import { MessageSquare, Mic, PhoneOff, Send } from 'lucide-react';
import { useRef, useState } from 'react';

import { createTestSession, createTextTurn } from '../../lib/api';
import { websocketUrl } from '../../lib/websocket';
import { Button } from '../ui/Button';
import { AudioMeter } from './AudioMeter';
import { TranscriptStream } from './TranscriptStream';

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

export function TestCallPanel({ agentId, open, onClose, onSessionUpdated }: TestCallPanelProps) {
  const socketRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const nextPlaybackTimeRef = useRef(0);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const gainRef = useRef<GainNode | null>(null);
  const microphoneStartedRef = useRef(false);
  const microphoneStartFallbackRef = useRef<number | null>(null);
  const [mode, setMode] = useState<TestMode>('voice');
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [active, setActive] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [textMessage, setTextMessage] = useState('');

  if (!open) return null;

  const appendEvent = (event: string) => {
    setEvents((current) => [...current.slice(-80), event]);
  };

  const clearMicrophoneStartFallback = () => {
    if (microphoneStartFallbackRef.current !== null) {
      window.clearTimeout(microphoneStartFallbackRef.current);
      microphoneStartFallbackRef.current = null;
    }
  };

  const cleanupPlayback = async () => {
    if (playbackContextRef.current && playbackContextRef.current.state !== 'closed') {
      await playbackContextRef.current.close();
    }
    playbackContextRef.current = null;
    nextPlaybackTimeRef.current = 0;
  };

  const playPcmChunk = async (chunk: ArrayBuffer) => {
    if (chunk.byteLength === 0) return;
    const context = playbackContextRef.current ?? new AudioContext({ sampleRate: 24000 });
    playbackContextRef.current = context;
    if (context.state === 'suspended') await context.resume();

    const samples = new Int16Array(chunk);
    const buffer = context.createBuffer(1, samples.length, 24000);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < samples.length; index += 1) {
      channel[index] = samples[index] / 32768;
    }

    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    const startAt = Math.max(context.currentTime + 0.02, nextPlaybackTimeRef.current);
    source.start(startAt);
    nextPlaybackTimeRef.current = startAt + buffer.duration;
  };

  const cleanupAudioInput = async () => {
    clearMicrophoneStartFallback();
    microphoneStartedRef.current = false;
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    gainRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current = null;
    gainRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      await audioContextRef.current.close();
    }
    audioContextRef.current = null;
  };

  const beginMicrophoneStreaming = (socket: WebSocket, stream: MediaStream, audioContext: AudioContext) => {
    if (microphoneStartedRef.current || socket.readyState !== WebSocket.OPEN) return;
    clearMicrophoneStartFallback();
    microphoneStartedRef.current = true;
    appendEvent('microphone.ready');
    startStreamingMicrophone(socket, stream, audioContext);
  };

  const beginMicrophoneAfterPlayback = (socket: WebSocket, stream: MediaStream, audioContext: AudioContext) => {
    const playbackContext = playbackContextRef.current;
    const queuedSeconds = playbackContext ? Math.max(0, nextPlaybackTimeRef.current - playbackContext.currentTime) : 0;
    clearMicrophoneStartFallback();
    microphoneStartFallbackRef.current = window.setTimeout(
      () => beginMicrophoneStreaming(socket, stream, audioContext),
      queuedSeconds * 1000 + 250,
    );
  };

  const startStreamingMicrophone = (socket: WebSocket, stream: MediaStream, audioContext: AudioContext) => {
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    const gain = audioContext.createGain();
    gain.gain.value = 0;

    processor.onaudioprocess = (event) => {
      if (socket.readyState !== WebSocket.OPEN) return;
      const samples = event.inputBuffer.getChannelData(0);
      const pcm = float32ToPcm16(samples);
      socket.send(pcm.buffer);
    };

    source.connect(processor);
    processor.connect(gain);
    gain.connect(audioContext.destination);
    sourceRef.current = source;
    processorRef.current = processor;
    gainRef.current = gain;
  };

  const startVoice = async () => {
    if (!agentId) {
      setError('Save an agent before starting a test call.');
      return;
    }
    setError(null);
    setAudioSrc(null);
    setEvents([]);
    setRunId(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioContext = new AudioContext();
      mediaStreamRef.current = stream;
      audioContextRef.current = audioContext;

      const session = await createTestSession(agentId);
      setRunId(session.run_id);
      const socket = new WebSocket(websocketUrl(session.websocket_url.replace('/ws/', '/stream/ws/')));
      socket.binaryType = 'arraybuffer';
      socketRef.current = socket;
      socket.onopen = () => {
        setActive(true);
        appendEvent(`session.open ${session.run_id}`);
        socket.send(JSON.stringify({ type: 'start', sample_rate: audioContext.sampleRate }));
        if (session.first_message?.trim()) {
          appendEvent('waiting.initial_greeting');
          microphoneStartFallbackRef.current = window.setTimeout(
            () => beginMicrophoneStreaming(socket, stream, audioContext),
            10000,
          );
        } else {
          beginMicrophoneStreaming(socket, stream, audioContext);
        }
      };
      socket.onmessage = (message) => {
        if (message.data instanceof ArrayBuffer) {
          void playPcmChunk(message.data).catch(() => {
            setError('Audio arrived, but browser playback failed.');
          });
          return;
        }
        const event = JSON.parse(message.data) as RuntimeMessage;
        appendEvent(formatRuntimeEvent(event));
        if (event.type === 'runtime.error') {
          setError(event.message ?? 'Runtime error while running the test call.');
          beginMicrophoneStreaming(socket, stream, audioContext);
        }
        if (event.type === 'audio.output.stopped') {
          beginMicrophoneAfterPlayback(socket, stream, audioContext);
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
        appendEvent('session.closed');
        onSessionUpdated();
        void cleanupAudioInput();
        void cleanupPlayback();
      };
    } catch (err) {
      await cleanupAudioInput();
      await cleanupPlayback();
      setError(err instanceof Error ? err.message : 'Unable to start test call.');
    }
  };

  const startText = async () => {
    if (!agentId) {
      setError('Save an agent before starting a chat session.');
      return;
    }
    stop();
    setMode('text');
    setError(null);
    setAudioSrc(null);
    setEvents([]);
    try {
      const session = await createTestSession(agentId);
      setRunId(session.run_id);
      setActive(true);
      appendEvent(`chat.open ${session.run_id}`);
      if (session.first_message) {
        appendEvent(`agent: ${session.first_message}`);
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
    appendEvent(`you: ${message}`);
    try {
      const turn = await createTextTurn(runId, message);
      appendEvent(`agent: ${turn.assistant_text}`);
      onSessionUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to send message.');
    } finally {
      setSending(false);
    }
  };

  const stop = () => {
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
    void cleanupAudioInput();
    void cleanupPlayback();
  };

  const closePanel = () => {
    stop();
    onClose();
  };

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
        <TranscriptStream events={events} />
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

function float32ToPcm16(samples: Float32Array) {
  const pcm = new Int16Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return pcm;
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
