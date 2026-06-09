import type { RunRecord } from '../../lib/types';

export function TraceTable({ run }: { run: RunRecord | null }) {
  const events = run?.trace_events ?? [];
  return (
    <div className="flex-1 overflow-auto">
      <table className="w-full border-collapse text-left">
        <thead className="sticky top-0 bg-off">
          <tr className="border-b border-line text-[10px] uppercase tracking-wide text-faint">
            <th className="px-3 py-2">#</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Payload</th>
            <th className="px-3 py-2">Time</th>
          </tr>
        </thead>
        <tbody>
          {events.length === 0 ? (
            <tr><td colSpan={4} className="px-4 py-10 text-center text-xs text-faint">No trace events captured yet.</td></tr>
          ) : events.map((event) => (
            <tr key={event.id} className="border-b border-line text-[11px] text-muted hover:bg-off">
              <td className="px-3 py-2 font-mono text-faint">{String(event.sequence).padStart(2, '0')}</td>
              <td className="px-3 py-2"><span className="rounded bg-blue-50 px-2 py-0.5 font-mono text-[10px] text-primary">{event.event_type}</span></td>
              <td className="px-3 py-2 font-mono">{JSON.stringify(event.payload)}</td>
              <td className="px-3 py-2 font-mono text-faint">{new Date(event.created_at).toLocaleTimeString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
