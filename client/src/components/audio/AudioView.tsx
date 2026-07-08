import { useEffect, useMemo, useState } from 'react';

import type { AgentRecord, AudioEvaluationRecord, Provider } from '../../lib/types';

interface AudioViewProps {
  agent: AgentRecord | null;
  records: AudioEvaluationRecord[];
}

const providers: Provider[] = ['deepgram', 'elevenlabs', 'sarvam'];

export function AudioView({ agent, records }: AudioViewProps) {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [latencyProvider, setLatencyProvider] = useState<Provider>('deepgram');

  useEffect(() => {
    if (records.length === 0) {
      setSelectedSessionId(null);
      return;
    }
    if (!selectedSessionId || !records.some((record) => record.session_id === selectedSessionId)) {
      setSelectedSessionId(records[0].session_id);
    }
  }, [records, selectedSessionId]);

  const selectedRecord = useMemo(
    () => records.find((record) => record.session_id === selectedSessionId) ?? records[0] ?? null,
    [records, selectedSessionId],
  );

  if (!agent) {
    return <EmptyPane title="Select an agent" body="Pick an agent from the sidebar to view recorded audio evaluations." />;
  }

  if (records.length === 0) {
    return (
      <EmptyPane
        title={`No audio evaluations for ${agent.name}`}
        body="Run a voice test with Evaluate mode enabled. Recorded audio sessions will appear here."
        agentName={agent.name}
      />
    );
  }

  const providerMetrics = selectedRecord?.provider_session_metrics[latencyProvider] ?? null;

  return (
    <div className="flex flex-1 overflow-hidden bg-off">
      <aside className="w-[320px] shrink-0 border-r border-line bg-white">
        <div className="border-b border-line px-4 py-3">
          <div className="text-[11px] text-faint">{agent.name} / Audio</div>
          <h1 className="mt-1 text-sm font-semibold text-text">Recorded audio sessions</h1>
          <p className="mt-1 text-xs text-faint">Each row is a reusable evaluation-ready audio session.</p>
        </div>
        <div className="overflow-y-auto p-3">
          <div className="space-y-2">
            {records.map((record) => {
              const active = record.session_id === selectedRecord?.session_id;
              return (
                <button
                  key={record.session_id}
                  onClick={() => setSelectedSessionId(record.session_id)}
                  className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                    active ? 'border-primary bg-blue-50 shadow-sm' : 'border-line bg-white hover:border-blue-200 hover:bg-off'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-semibold text-text">{record.session_id.slice(0, 18)}...</div>
                      <div className="mt-1 text-[11px] text-faint">{formatDate(record.created_at)}</div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${record.evaluate_mode ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                      {record.evaluate_mode ? 'Eval on' : 'Capture only'}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-muted">
                    <div>
                      <div className="text-faint">Turns</div>
                      <div className="font-semibold text-text">{record.turn_count}</div>
                    </div>
                    <div>
                      <div className="text-faint">Duration</div>
                      <div className="font-semibold text-text">{formatDuration(record.session_stt_duration_sec)}</div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col overflow-y-auto p-6">
        {selectedRecord ? (
          <>
            <div className="mb-5 flex items-end justify-between gap-4">
              <div>
                <div className="text-[11px] text-faint">{agent.name} / Audio / {selectedRecord.run_id.slice(0, 8)}</div>
                <h2 className="mt-1 text-xl font-semibold text-text">Audio evaluation dashboard</h2>
                <p className="mt-1 text-sm text-faint">
                  Session-level cost across all provider models, with latency summarized from real per-turn provider calls.
                </p>
              </div>
              <label className="rounded-xl border border-line bg-white px-3 py-2 text-xs shadow-sm">
                <span className="mr-2 font-medium text-muted">Latency provider</span>
                <select
                  className="bg-transparent text-text outline-none"
                  value={latencyProvider}
                  onChange={(event) => setLatencyProvider(event.target.value as Provider)}
                >
                  {providers.map((provider) => (
                    <option key={provider} value={provider}>
                      {titleCase(provider)}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="mb-5 grid grid-cols-4 gap-4">
              <MetricCard label="Turns" value={String(selectedRecord.turn_count)} sub="captured user turns" />
              <MetricCard label="Duration" value={formatDuration(selectedRecord.session_stt_duration_sec)} sub="session STT duration" />
              <MetricCard label="Latency median" value={formatLatency(providerMetrics?.latency_median_ms ?? 0)} sub={`${titleCase(latencyProvider)} p50`} />
              <MetricCard label="Latency p95" value={formatLatency(providerMetrics?.latency_p95_ms ?? 0)} sub={`${titleCase(latencyProvider)} p95`} />
            </div>

            <div className="mb-5 rounded-2xl border border-line bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-text">Provider latency summary</h3>
                  <p className="mt-1 text-xs text-faint">Real per-turn latencies rolled up into session-level reporting.</p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                {providers.map((provider) => {
                  const metrics = selectedRecord.provider_session_metrics[provider];
                  return (
                    <div key={provider} className="rounded-xl border border-line bg-off p-4">
                      <div className="text-sm font-semibold text-text">{titleCase(provider)}</div>
                      <div className="mt-3 space-y-2 text-xs text-muted">
                        <Row label="Calls" value={String(metrics?.call_count ?? 0)} />
                        <Row label="Success" value={String(metrics?.success_count ?? 0)} />
                        <Row label="Errors" value={String(metrics?.error_count ?? 0)} />
                        <Row label="Avg" value={formatLatency(metrics?.latency_avg_ms ?? 0)} />
                        <Row label="Median" value={formatLatency(metrics?.latency_median_ms ?? 0)} />
                        <Row label="P95" value={formatLatency(metrics?.latency_p95_ms ?? 0)} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-text">Cost across all provider models</h3>
                <p className="mt-1 text-xs text-faint">Computed from this audio session’s total user-turn duration. No extra provider calls required.</p>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                {Object.entries(selectedRecord.session_model_costs_usd).map(([provider, models]) => (
                  <div key={provider} className="rounded-xl border border-line bg-off p-4">
                    <div className="mb-3 text-sm font-semibold text-text">{titleCase(provider)}</div>
                    <div className="space-y-2 text-xs">
                      {Object.entries(models).map(([model, cost]) => (
                        <div key={model} className="flex items-center justify-between gap-3 rounded-lg bg-white px-3 py-2">
                          <span className="font-medium text-muted">{model}</span>
                          <span className="font-mono text-text">${cost.toFixed(6)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}

function MetricCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white p-4 shadow-sm">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-faint">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-text">{value}</div>
      <div className="mt-1 text-xs text-faint">{sub}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-faint">{label}</span>
      <span className="font-medium text-text">{value}</span>
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatDuration(seconds: number) {
  return `${seconds.toFixed(2)}s`;
}

function formatLatency(value: number) {
  return `${value.toFixed(1)} ms`;
}

function titleCase(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function EmptyPane({ title, body, agentName }: { title: string; body: string; agentName?: string }) {
  return (
    <div className="flex-1 overflow-auto bg-off p-6">
      {agentName ? (
        <div className="mb-3 text-[11px] text-faint">
          <span className="text-muted">{agentName}</span>
          <span className="mx-1.5">/</span>
          <span>Audio</span>
        </div>
      ) : null}
      <div className="max-w-5xl rounded-lg border border-dashed border-line bg-white p-8 text-center">
        <div className="text-sm font-semibold text-text">{title}</div>
        <p className="mt-1 text-xs text-faint">{body}</p>
      </div>
    </div>
  );
}
