import { MetricCard } from '../ui/MetricCard';
import { aggregate, formatCost, formatDuration } from '../../lib/analytics';
import type { AgentRecord, RunRecord } from '../../lib/types';

interface ReportsViewProps {
  runs: RunRecord[];
  agent: AgentRecord | null;
}

export function ReportsView({ runs, agent }: ReportsViewProps) {
  if (!agent) {
    return (
      <EmptyShell title="Select an agent" body="Pick an agent from the sidebar to view its reports." />
    );
  }

  const summary = aggregate(runs);

  if (summary.conversations === 0) {
    return (
      <EmptyShell
        title={`No conversations for ${agent.name} yet`}
        body="Run a test call from the Builder view. Aggregate cost, duration, and token stats will populate here."
        agentName={agent.name}
      />
    );
  }

  return (
    <div className="flex-1 overflow-auto bg-off p-6">
      <Breadcrumb agentName={agent.name} />
      <div className="mb-5">
        <h1 className="text-lg font-semibold">Reports</h1>
        <p className="mt-1 text-xs text-faint">
          Aggregated across every conversation for <span className="font-medium text-text">{agent.name}</span>. Cost
          is derived from provider-reported usage (Gemini tokens, Deepgram audio-seconds and characters).
        </p>
      </div>

      <div className="mb-4 grid max-w-5xl grid-cols-3 overflow-hidden rounded-lg border border-line bg-white">
        <MetricCard
          label="Conversations"
          value={summary.conversations.toLocaleString()}
          sub="total sessions"
        />
        <MetricCard
          label="Avg duration"
          value={formatDuration(summary.avgDurationSec)}
          sub="mm:ss per session"
        />
        <MetricCard
          label="Total cost"
          value={formatCost(summary.totalCostUsd)}
          sub={`${formatCost(summary.avgCostUsd)} avg`}
        />
        <MetricCard
          label="Total LLM cost"
          value={formatCost(summary.totalLlmCostUsd)}
          sub={`${formatCost(summary.avgLlmCostUsd)} avg`}
        />
        <MetricCard
          label="Total tokens"
          value={summary.totalTokens.toLocaleString()}
          sub="prompt + completion"
        />
        <MetricCard
          label="Cost per minute"
          value={formatCost(costPerMinute(summary), 4)}
          sub="blended across sessions"
        />
      </div>

      <div className="max-w-5xl rounded-lg border border-line bg-white px-4 py-3 text-[11px] text-muted">
        <span className="mr-1 text-faint">Breakdown:</span>
        <span>LLM {formatCost(summary.totalLlmCostUsd)}</span>
        <span className="mx-2 text-faint">·</span>
        <span>STT {formatCost(summary.totalSttCostUsd)}</span>
        <span className="mx-2 text-faint">·</span>
        <span>TTS {formatCost(summary.totalTtsCostUsd)}</span>
        <span className="mx-2 text-faint">·</span>
        <span className="font-semibold text-text">Total {formatCost(summary.totalCostUsd)}</span>
      </div>
    </div>
  );
}

function Breadcrumb({ agentName }: { agentName: string }) {
  return (
    <div className="mb-3 text-[11px] text-faint">
      <span className="text-muted">{agentName}</span>
      <span className="mx-1.5">/</span>
      <span>Reports</span>
    </div>
  );
}

function EmptyShell({ title, body, agentName }: { title: string; body: string; agentName?: string }) {
  return (
    <div className="flex-1 overflow-auto bg-off p-6">
      {agentName ? <Breadcrumb agentName={agentName} /> : null}
      <div className="max-w-5xl rounded-lg border border-dashed border-line bg-white p-8 text-center">
        <div className="text-sm font-semibold text-text">{title}</div>
        <p className="mt-1 text-xs text-faint">{body}</p>
      </div>
    </div>
  );
}

function costPerMinute(summary: ReturnType<typeof aggregate>): number {
  const totalMinutes = (summary.avgDurationSec * summary.conversations) / 60;
  if (totalMinutes <= 0) return 0;
  return summary.totalCostUsd / totalMinutes;
}
