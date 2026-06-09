export function TranscriptStream({ events }: { events: string[] }) {
  return (
    <div className="min-h-[180px] rounded-lg border border-line bg-white p-3 font-mono text-[11px] leading-5 text-muted">
      {events.length === 0 ? <span className="text-faint">No session events yet.</span> : events.map((event, index) => <div key={`${event}-${index}`}>{event}</div>)}
    </div>
  );
}
