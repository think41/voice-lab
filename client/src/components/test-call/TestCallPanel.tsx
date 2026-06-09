import { Mic, PhoneOff } from 'lucide-react';
import { useRef, useState } from 'react';

import { createTestSession } from '../../lib/api';
import { websocketUrl } from '../../lib/websocket';
import { Button } from '../ui/Button';
import { AudioMeter } from './AudioMeter';
import { TranscriptStream } from './TranscriptStream';

interface TestCallPanelProps {
  agentId: string | null;
  open: boolean;
  onClose: () => void;
}

type RuntimeMessage = {
  type?: string;
  text?: string;
  audio_base64?: string;
  mime_type?: string;
  message?: string;
  sample_rate?: number;
};

export function TestCallPanel({ agentId, open, onClose }: TestCallPanelProps) {
  const socketRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const gainRef = useRef<GainNode | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioSrc, setAudioSrc] = useState<string | null>(null);

  if (!open) return null;

  const appendEvent = (event: string) => {
    setEvents((current) => [...current.slice(-80), event]);
  };

  const cleanupAudioInput = async () => {
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

  const start = async () => {
    if (!agentId) {
      setError('Save an agent before starting a test call.');
      return;
    }
    setError(null);
    setAudioSrc(null);
    setEvents([]);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioContext = new AudioContext();
      mediaStreamRef.current = stream;
      audioContextRef.current = audioContext;

      const session = await createTestSession(agentId);
      const socket = new WebSocket(websocketUrl(session.websocket_url));
      socketRef.current = socket;
      socket.onopen = () => {
        setActive(true);
        appendEvent(`session.open ${session.run_id}`);
        socket.send(JSON.stringify({ type: 'start', sample_rate: audioContext.sampleRate }));
        startStreamingMicrophone(socket, stream, audioContext);
      };
      socket.onmessage = (message) => {
        const event = JSON.parse(message.data) as RuntimeMessage;
        appendEvent(formatRuntimeEvent(event));
        if (event.type === 'runtime.error') {
          setError(event.message ?? 'Runtime error while running the test call.');
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
        void cleanupAudioInput();
      };
    } catch (err) {
      await cleanupAudioInput();
      setError(err instanceof Error ? err.message : 'Unable to start test call.');
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
    void cleanupAudioInput();
  };

  const closePanel = () => {
    stop();
    onClose();
  };

  return (
    <div className="absolute right-4 top-[68px] z-40 w-[360px] rounded-xl border border-line bg-white shadow-panel">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Test call</h2>
          <p className="text-[11px] text-faint">Runs the latest saved UI agent config.</p>
        </div>
        <button className="text-faint hover:text-text" onClick={closePanel}>Close</button>
      </div>
      <div className="space-y-4 p-4">
        <AudioMeter active={active} />
        <TranscriptStream events={events} />
        {audioSrc ? <audio className="w-full" controls src={audioSrc} /> : null}
        {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-danger">{error}</div> : null}
        <div className="flex gap-2">
          <Button className="flex-1" variant="primary" icon={<Mic size={14} />} onClick={start} disabled={active}>Start</Button>
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
  if (event.type === 'runtime.ready') {
    return `runtime.ready ${event.sample_rate ? `${event.sample_rate}hz` : ''}`.trim();
  }
  if (event.type === 'runtime.error') {
    return `runtime.error: ${event.message ?? 'unknown error'}`;
  }
  return event.type ?? JSON.stringify(event);
}
