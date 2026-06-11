import { useEffect, useRef } from 'react';

export function TranscriptStream({ events }: { events: string[] }) {
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!streamRef.current) return;
    streamRef.current.scrollTop = streamRef.current.scrollHeight;
  }, [events]);

  return (
    <div
      ref={streamRef}
      className="min-h-[180px] max-h-[320px] overflow-y-auto rounded-lg border border-line bg-white p-3 font-mono text-[11px] leading-5 text-muted"
    >
      {events.length === 0 ? <span className="text-faint">No session events yet.</span> : events.map((event, index) => <div key={`${event}-${index}`}>{event}</div>)}
    </div>
  );
}
