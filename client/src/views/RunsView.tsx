import { MetricCard } from '../components/ui/MetricCard';
import { SessionsPane } from '../components/runs/SessionsPane';
import { TraceTable } from '../components/runs/TraceTable';
import type { RunRecord } from '../lib/types';

export function RunsView({ runs }: { runs: RunRecord[] }) {
  const selectedRun = runs[0] ?? null;
  return (
    <div className="flex flex-1 overflow-hidden">
      <SessionsPane runs={runs} />
      <section className="flex min-w-0 flex-1 flex-col bg-white">
        <div className="grid grid-cols-4 border-b border-line">
          <MetricCard label="Session cost" value="$0.00" sub={selectedRun?.id.slice(0, 8) ?? 'no session'} />
          <MetricCard label="Avg turn latency" value="0ms" sub="p95 unavailable" />
          <MetricCard label="Total tokens" value="0" sub="tracked by ADK session" />
          <MetricCard label="Trace events" value={String(selectedRun?.trace_events.length ?? 0)} sub="captured locally" />
        </div>
        <TraceTable run={selectedRun} />
      </section>
    </div>
  );
}
