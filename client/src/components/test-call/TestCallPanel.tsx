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

export function TestCallPanel({ agentId, open, onClose }: TestCallPanelProps) {
  const socketRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const start = async () => {
    if (!agentId) {
      setError('Save an agent before starting a test call.');
      return;
    }
    setError(null);
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      const session = await createTestSession(agentId);
      const socket = new WebSocket(websocketUrl(session.websocket_url));
      socketRef.current = socket;
      socket.onopen = () => {
        setActive(true);
        socket.send(JSON.stringify({ type: 'start' }));
      };
      socket.onmessage = (message) => {
        setEvents((current) => [...current, message.data]);
        const event = JSON.parse(message.data) as {
          type?: string;
          audio_base64?: string;
          mime_type?: string;
        };
        if (event.type === 'audio.output' && event.audio_base64) {
          audioRef.current?.pause();
          audioRef.current = new Audio(
            `data:${event.mime_type ?? 'audio/mpeg'};base64,${event.audio_base64}`
          );
          void audioRef.current.play().catch(() => {
            setError('Browser blocked audio playback. Press Start again or allow site audio.');
          });
        }
      };
      socket.onclose = () => setActive(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start test call.');
    }
  };

  const stop = () => {
    socketRef.current?.close();
    socketRef.current = null;
    audioRef.current?.pause();
    audioRef.current = null;
    setActive(false);
  };

  return (
    <div className="absolute right-4 top-[68px] z-40 w-[360px] rounded-xl border border-line bg-white shadow-panel">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Test call</h2>
          <p className="text-[11px] text-faint">Runs the latest saved UI agent config.</p>
        </div>
        <button className="text-faint hover:text-text" onClick={onClose}>Close</button>
      </div>
      <div className="space-y-4 p-4">
        <AudioMeter active={active} />
        <TranscriptStream events={events} />
        {error ? <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-danger">{error}</div> : null}
        <div className="flex gap-2">
          <Button className="flex-1" variant="primary" icon={<Mic size={14} />} onClick={start} disabled={active}>Start</Button>
          <Button className="flex-1" variant="danger" icon={<PhoneOff size={14} />} onClick={stop}>Stop</Button>
        </div>
      </div>
    </div>
  );
}
