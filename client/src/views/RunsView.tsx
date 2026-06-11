import { useEffect, useState } from 'react';

import { MetricCard } from '../components/ui/MetricCard';
import { SessionsPane } from '../components/runs/SessionsPane';
import { TraceTable } from '../components/runs/TraceTable';
import type { RunRecord } from '../lib/types';

export function RunsView({ runs }: { runs: RunRecord[] }) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  useEffect(() => {
    if (runs.length === 0) {
      setSelectedRunId(null);
      return;
    }
    if (!selectedRunId || !runs.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(runs[0].id);
    }
  }, [runs, selectedRunId]);

  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? runs[0] ?? null;

  // Calculate session metrics from trace events
  const metrics = (() => {
    if (!selectedRun) return { cost: '$0.00', latency: '0ms', tokens: '0', events: '0' };
    
    const events = selectedRun.trace_events;
    let totalTokens = 0;
    let totalLatencyMs = 0;
    let turnCount = 0;

    // Token estimation (rough: 4 chars per token)
    events.forEach(event => {
      const text = (event.payload.text as string) || '';
      if (text) totalTokens += Math.ceil(text.length / 4);
    });

    // Latency calculation: time between transcript.final and the first agent.text after it
    for (let i = 0; i < events.length; i++) {
      if (events[i].event_type === 'transcript.final') {
        const nextAgentText = events.slice(i + 1).find(e => e.event_type === 'agent.text');
        if (nextAgentText) {
          const start = new Date(events[i].created_at).getTime();
          const end = new Date(nextAgentText.created_at).getTime();
          totalLatencyMs += (end - start);
          turnCount++;
        }
      }
    }

    const avgLatency = turnCount > 0 ? Math.round(totalLatencyMs / turnCount) : 0;
    // Simple cost model: $0.01 per 1k tokens
    const estimatedCost = (totalTokens / 1000) * 0.01;

    return {
      cost: `$${estimatedCost.toFixed(2)}`,
      latency: `${avgLatency}ms`,
      tokens: String(totalTokens),
      events: String(events.length)
    };
  })();

  return (
    <div className="flex flex-1 overflow-hidden">
      <SessionsPane runs={runs} selectedRunId={selectedRun?.id ?? null} onSelectRun={setSelectedRunId} />
      <section className="flex min-w-0 flex-1 flex-col bg-white">
        <div className="grid grid-cols-4 border-b border-line">
          <MetricCard label="Session cost" value={metrics.cost} sub={selectedRun?.id.slice(0, 8) ?? 'no session'} />
          <MetricCard label="Avg turn latency" value={metrics.latency} sub="p95 unavailable" />
          <MetricCard label="Total tokens" value={metrics.tokens} sub="tracked by ADK session" />
          <MetricCard label="Trace events" value={metrics.events} sub="captured locally" />
        </div>
        <TraceTable run={selectedRun} />
      </section>
    </div>
  );
}
