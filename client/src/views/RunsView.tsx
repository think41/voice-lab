import { useEffect, useState } from 'react';

import { SessionsPane } from '../components/runs/SessionsPane';
import { TraceTable } from '../components/runs/TraceTable';
import type { AgentRecord, RunRecord } from '../lib/types';

interface RunsViewProps {
  agent: AgentRecord | null;
  runs: RunRecord[];
}

export function RunsView({ agent, runs }: RunsViewProps) {
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

  if (!agent) {
    return (
      <EmptyPane title="Select an agent" body="Pick an agent from the sidebar to view its conversations." />
    );
  }

  if (runs.length === 0) {
    return (
      <EmptyPane
        title={`No conversations for ${agent.name}`}
        body="Run a test call from the Builder view. Stored conversations will appear here by session id."
      />
    );
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <SessionsPane runs={runs} selectedRunId={selectedRun?.id ?? null} onSelectRun={setSelectedRunId} />
      <section className="flex min-w-0 flex-1 flex-col bg-white">
        <div className="border-b border-line px-4 py-2 text-[11px] text-faint">
          <span className="text-muted">{agent.name}</span>
          <span className="mx-1.5">/</span>
          <span>Conversations</span>
          {selectedRun ? (
            <>
              <span className="mx-1.5">/</span>
              <span className="font-mono text-text">{selectedRun.adk_session_id}</span>
            </>
          ) : null}
        </div>
        <TraceTable run={selectedRun} />
      </section>
    </div>
  );
}

function EmptyPane({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-1 items-center justify-center bg-off p-6">
      <div className="max-w-md rounded-lg border border-dashed border-line bg-white p-8 text-center">
        <div className="text-sm font-semibold text-text">{title}</div>
        <p className="mt-1 text-xs text-faint">{body}</p>
      </div>
    </div>
  );
}
