import type { RunRecord } from '../../lib/types';

interface SessionsPaneProps {
  runs: RunRecord[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
}

export function SessionsPane({ runs, selectedRunId, onSelectRun }: SessionsPaneProps) {
  return (
    <aside className="w-60 shrink-0 overflow-y-auto border-r border-line bg-white">
      <div className="flex justify-between border-b border-line px-3.5 py-3 text-[11px] font-semibold text-muted">
        <span>{runs.length} sessions</span>
        <span className="text-faint">7 days</span>
      </div>
      {runs.length === 0 ? <div className="p-4 text-xs text-faint">No runs yet.</div> : null}
      {runs.map((run) => {
        const selected = run.id === selectedRunId;
        return (
          <button
            key={run.id}
            type="button"
            className={`flex w-full items-center gap-2 border-b border-line px-3.5 py-3 text-left transition ${selected ? 'border-l-2 border-l-primary bg-blue-50/60' : 'hover:bg-off'}`}
            onClick={() => onSelectRun(run.id)}
          >
            <span className={`h-2 w-2 rounded-full ${run.status === 'error' ? 'bg-danger' : 'bg-success'}`} />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-mono text-[11px] font-semibold">{run.id.slice(0, 8)}</span>
              <span className="block text-[10px] text-faint">{run.trace_events.length} steps</span>
            </span>
            <span className="font-mono text-[11px] font-semibold text-primary">{run.status}</span>
          </button>
        );
      })}
    </aside>
  );
}
