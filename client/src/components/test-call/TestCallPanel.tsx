import { MessageSquare, Mic, PhoneOff, Send } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { createTestSession, createTextTurn } from '../../lib/api';
import { websocketUrl } from '../../lib/websocket';
import { Button } from '../ui/Button';
import { AudioMeter } from './AudioMeter';
import { ChatMessage, TranscriptStream } from './TranscriptStream';
import { useAudioIO } from './useAudioIO';

interface TestCallPanelProps {
  agentId: string | null;
  open: boolean;
  onClose: () => void;
  onSessionUpdated: () => void;
}

type TestMode = 'voice' | 'text';

type RuntimeMessage = {
  type?: string;
  text?: string;
  audio_base64?: string;
  mime_type?: string;
  message?: string;
  sample_rate?: number;
};

type PanelSnapshot = {
  mode: TestMode;
  runId: string | null;
  messages: ChatMessage[];
  audioSrc: string | null;
  textMessage: string;
};

export function TestCallPanel({ agentId, open, onClose, onSessionUpdated }: TestCallPanelProps) {
  const socketRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const agentSnapshotsRef = useRef<Record<string, PanelSnapshot>>({});
  const previousAgentIdRef = useRef<string | null>(agentId);
  const [mode, setMode] = useState<TestMode>('voice');
  const [runId, setRunId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [active, setActive] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [textMessage, setTextMessage] = useState('');

  const appendLog = (event: string) => {
    console.debug('[test-call]', event);
  };

  const appendMessage = (role: ChatMessage['role'], message: string) => {
    const text = message.trim();
    if (!text) return;
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role, text },
    ].slice(-40));
  };

  const appendAssistantDelta = (delta: string) => {
    const text = delta.trim();
    if (!text) return;
    setMessages((current) => {
      const last = current[current.length - 1];
      if (last?.role === 'assistant') {
        const separator = /\s$/.test(last.text) || /^[.,!?;:]/.test(text) ? '' : ' ';
        return [
          ...current.slice(0, -1),
          { ...last, text: last.text + separator + text },
        ];
      }
      return [...current, { id: crypto.randomUUID(), role: 'assistant' as const, text }].slice(-40);
    });
  };

  const handleRuntimeEvent = (event: RuntimeMessage) => {
    if (event.type === 'transcript.final' && event.text) {
      appendMessage('user', event.text);
      return;
    }
    if (event.type === 'agent.text' && event.text) {
      appendMessage('assistant', event.text);
      return;
    }
    if (event.type === 'agent.text.delta' && event.text) {
      appendAssistantDelta(event.text);
      return;
    }
    appendLog(formatRuntimeEvent(event));
  };

  const audio = useAudioIO({
    onCapture: (chunk) => {
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) socket.send(chunk);
    },
    onCaptureStarted: () => appendLog('microphone.ready'),
    onError: (message) => setError(message),
  });

  const stopSession = () => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: 'stop' }));
    }
    socketRef.current?.close();
    socketRef.current = null;
    audioRef.current?.pause();
    audioRef.current = null;
    setAudioSrc(null);
    setActive(false);
    onSessionUpdated();
    void audio.cleanup();
  };

  useEffect(() => {
    return () => {
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        try {
          socketRef.current.send(JSON.stringify({ type: 'stop' }));
        } catch {
          // ignore best-effort shutdown errors during unmount
        }
      }
      socketRef.current?.close();
      socketRef.current = null;
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (open || (!socketRef.current && !active)) return;
    stopSession();
  }, [open, active]);

  useEffect(() => {
    const previousAgentId = previousAgentIdRef.current;
    if (previousAgentId === agentId) return;

    if (previousAgentId) {
      agentSnapshotsRef.current[previousAgentId] = {
        mode,
        runId,
        messages,
        audioSrc,
        textMessage,
      };
    }

    if (agentId) {
      const snapshot = agentSnapshotsRef.current[agentId];
      if (snapshot) {
        setMode(snapshot.mode);
        setRunId(snapshot.runId);
        setMessages(snapshot.messages);
        setAudioSrc(snapshot.audioSrc);
        setTextMessage(snapshot.textMessage);
      } else {
        setMode('voice');
        setRunId(null);
        setMessages([]);
        setAudioSrc(null);
        setTextMessage('');
      }
    } else {
      setMode('voice');
      setRunId(null);
      setMessages([]);
      setAudioSrc(null);
      setTextMessage('');
    }

    setActive(false);
    setSending(false);
    setError(null);
    previousAgentIdRef.current = agentId;
  }, [agentId, mode, runId, messages, audioSrc, textMessage]);

  const startVoice = async () => {
    if (!agentId) {
      setError('Save an agent before starting a test call.');
      return;
    }
    setError(null);
    setAudioSrc(null);
    setMessages([]);
    setRunId(null);
    try {
      const audioContext = await audio.acquireMic();
      const session = await createTestSession(agentId);
      setRunId(session.run_id);
      const socket = new WebSocket(websocketUrl(session.websocket_url.replace('/ws/', '/stream/ws/')));
      socket.binaryType = 'arraybuffer';
      socketRef.current = socket;
      socket.onopen = () => {
        setActive(true);
        appendLog(`session.open ${session.run_id}`);
        socket.send(JSON.stringify({ type: 'start', sample_rate: audioContext.sampleRate }));
        audio.scheduleCapture(Boolean(session.first_message?.trim()));
      };
      socket.onmessage = (message) => {
        if (message.data instanceof ArrayBuffer) {
          void audio.enqueuePlayback(message.data);
          return;
        }
        const event = JSON.parse(message.data) as RuntimeMessage;
        handleRuntimeEvent(event);
        if (event.type === 'runtime.error') {
          setError(event.message ?? 'Runtime error while running the test call.');
          audio.forceCaptureStart();
        }
        if (event.type === 'audio.output.stopped') {
          audio.signalServerStopped();
        }
        if (event.type === 'audio.output' && event.audio_base64) {
          audioRef.current?.pause();
          const src = `data:${event.mime_type ?? 'audio/mpeg'};base64,${event.audio_base64}`;
          setAudioSrc(src);
          audioRef.current = new Audio(src);
          void audioRef.current.play().catch(() => {
            setError('Audio arrived, but browser playback was blocked. Use the audio controls below.');
          });
        }
      };
      socket.onerror = () => setError('WebSocket failed. Check the FastAPI terminal logs.');
      socket.onclose = () => {
        setActive(false);
        appendLog('session.closed');
        onSessionUpdated();
        void audio.cleanup();
      };
    } catch (err) {
      await audio.cleanup();
      setError(err instanceof Error ? err.message : 'Unable to start test call.');
    }
  };

  const startText = async () => {
    if (!agentId) {
      setError('Save an agent before starting a chat session.');
      return;
    }
    stopSession();
    setMode('text');
    setError(null);
    setAudioSrc(null);
    setMessages([]);
    try {
      const session = await createTestSession(agentId);
      setRunId(session.run_id);
      setActive(true);
      appendLog(`chat.open ${session.run_id}`);
      if (session.first_message) {
        appendMessage('assistant', session.first_message);
      }
      onSessionUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start chat session.');
    }
  };

  const sendText = async () => {
    const message = textMessage.trim();
    if (!message || !runId) return;
    setSending(true);
    setError(null);
    setTextMessage('');
    appendMessage('user', message);
    try {
      const turn = await createTextTurn(runId, message);
      appendMessage('assistant', turn.assistant_text);
      onSessionUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to send message.');
    } finally {
      setSending(false);
    }
  };

  const stop = () => {
    stopSession();
  };

  const closePanel = () => {
    stopSession();
    onClose();
  };

  if (!open) return null;

  return (
    <div className="absolute right-4 top-[68px] z-40 w-[380px] rounded-xl border border-line bg-white shadow-panel">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Test agent</h2>
          <p className="text-[11px] text-faint">Runs the latest saved UI agent config.</p>
        </div>
        <button className="text-faint hover:text-text" onClick={closePanel}>Close</button>
      </div>
      <div className="space-y-4 p-4">
        <div className="grid grid-cols-2 rounded-lg border border-line bg-off p-1 text-xs font-semibold">
          <button className={`rounded-md px-2 py-1.5 ${mode === 'voice' ? 'bg-white text-text shadow-sm' : 'text-faint'}`} onClick={() => setMode('voice')}>Voice</button>
          <button className={`rounded-md px-2 py-1.5 ${mode === 'text' ? 'bg-white text-text shadow-sm' : 'text-faint'}`} onClick={() => setMode('text')}>Text</button>
        </div>
        {mode === 'voice' ? <AudioMeter active={active} /> : null}
        <TranscriptStream messages={messages} />
        {mode === 'text' ? (
          <div className="flex gap-2">
            <input
              className="min-w-0 flex-1 rounded-md border border-line px-3 py-2 text-xs outline-none focus:border-primary"
              value={textMessage}
              placeholder={runId ? 'Type a message...' : 'Start text chat first'}
              disabled={!runId || sending}
              onChange={(event) => setTextMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void sendText();
              }}
            />
            <Button variant="primary" icon={<Send size={14} />} onClick={sendText} disabled={!runId || sending || !textMessage.trim()}>Send</Button>
          </div>
        ) : null}
        {audioSrc ? <audio className="w-full" controls src={audioSrc} /> : null}
        {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-danger">{error}</div> : null}
        <div className="flex gap-2">
          {mode === 'voice' ? (
            <Button className="flex-1" variant="primary" icon={<Mic size={14} />} onClick={startVoice} disabled={active}>Start voice</Button>
          ) : (
            <Button className="flex-1" variant="primary" icon={<MessageSquare size={14} />} onClick={startText} disabled={active}>Start text</Button>
          )}
          <Button className="flex-1" variant="danger" icon={<PhoneOff size={14} />} onClick={stop}>Stop</Button>
        </div>
      </div>
    </div>
  );
}

function formatRuntimeEvent(event: RuntimeMessage) {
  if (event.type === 'audio.output') {
    return `audio.output ${event.text ? `${event.text.length} chars` : 'received'}`;
  }
  if (event.type === 'transcript.partial' && event.text) {
    return `you.partial: ${event.text}`;
  }
  if (event.type === 'transcript.final' && event.text) {
    return `you: ${event.text}`;
  }
  if (event.type === 'agent.text' && event.text) {
    return `agent: ${event.text}`;
  }
  if (event.type === 'agent.text.delta' && event.text) {
    return `agent.delta: ${event.text}`;
  }
  if (event.type === 'agent.thinking') {
    return 'agent.thinking';
  }
  if (event.type === 'audio.output.started') {
    return 'audio.output.started';
  }
  if (event.type === 'audio.output.stopped') {
    return 'audio.output.stopped';
  }
  if (event.type === 'runtime.ready') {
    return `runtime.ready ${event.sample_rate ? `${event.sample_rate}hz` : ''}`.trim();
  }
  if (event.type === 'runtime.error') {
    return `runtime.error: ${event.message ?? 'unknown error'}`;
  }
  return event.type ?? JSON.stringify(event);
}
