import type { RunRecord } from '../../lib/types';

export function SessionsPane({ runs }: { runs: RunRecord[] }) {
  return (
    <aside className="w-60 shrink-0 overflow-y-auto border-r border-line bg-white">
      <div className="flex justify-between border-b border-line px-3.5 py-3 text-[11px] font-semibold text-muted">
        <span>{runs.length} sessions</span>
        <span className="text-faint">7 days</span>
      </div>
      {runs.length === 0 ? <div className="p-4 text-xs text-faint">No runs yet.</div> : null}
      {runs.map((run, index) => (
        <div key={run.id} className={`flex items-center gap-2 border-b border-line px-3.5 py-3 ${index === 0 ? 'border-l-2 border-l-primary bg-blue-50/60' : 'hover:bg-off'}`}>
          <span className={`h-2 w-2 rounded-full ${run.status === 'error' ? 'bg-danger' : 'bg-success'}`} />
          <div className="min-w-0 flex-1">
            <div className="truncate font-mono text-[11px] font-semibold">{run.id.slice(0, 8)}</div>
            <div className="text-[10px] text-faint">{run.trace_events.length} steps</div>
          </div>
          <div className="font-mono text-[11px] font-semibold text-primary">{run.status}</div>
        </div>
      ))}
    </aside>
  );
}
