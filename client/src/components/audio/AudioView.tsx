import { useEffect, useMemo, useState } from 'react';

import type { AgentRecord, AudioEvaluationRecord, SessionConfigInfo } from '../../lib/types';

interface AudioViewProps {
  agent: AgentRecord | null;
  records: AudioEvaluationRecord[];
}

export function AudioView({ agent, records }: AudioViewProps) {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

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

  const hasLlmUsage = Boolean(
    selectedRecord &&
      (selectedRecord.session_llm_prompt_tokens > 0 || selectedRecord.session_llm_completion_tokens > 0),
  );

  if (!agent) {
    return <EmptyPane title="Select an agent" body="Pick an agent from the sidebar to view its metrics dashboard." />;
  }

  if (records.length === 0) {
    return (
      <EmptyPane
        title={`No audio evaluations for ${agent.name}`}
        body="Run a voice test. Recorded audio sessions will appear here."
        agentName={agent.name}
      />
    );
  }

  return (
    <div className="flex flex-1 overflow-hidden bg-off">
      <aside className="w-[320px] shrink-0 border-r border-line bg-white">
        <div className="border-b border-line px-4 py-3">
          <div className="text-[11px] text-faint">{agent.name} / Metrics</div>
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
            <div className="mb-5">
              <div className="text-[11px] text-faint">{agent.name} / Metrics / {selectedRecord.run_id.slice(0, 8)}</div>
              <h2 className="mt-1 text-xl font-semibold text-text">Metrics dashboard</h2>
              <p className="mt-1 text-sm text-faint">
                Session-level usage and cost across LLM, STT, and TTS for this recorded session.
              </p>
            </div>

            <SessionConfigStrip config={selectedRecord.session_config} />

            {hasLlmUsage ? (
              <>
                <SectionHeader label="LLM" />
                <div className="mb-5 grid grid-cols-3 gap-4">
                  <MetricCard
                    label="Prompt Tokens"
                    value={selectedRecord.session_llm_prompt_tokens.toLocaleString()}
                    sub="input tokens sent"
                  />
                  <MetricCard
                    label="Completion Tokens"
                    value={selectedRecord.session_llm_completion_tokens.toLocaleString()}
                    sub="output tokens generated"
                  />
                  <MetricCard
                    label="LLM Cost"
                    value={
                      selectedRecord.session_llm_cost_usd != null
                        ? `$${selectedRecord.session_llm_cost_usd.toFixed(6)}`
                        : 'n/a'
                    }
                    sub={selectedRecord.session_config?.llm_model ?? 'actual model used'}
                  />
                </div>

                {Object.keys(selectedRecord.session_llm_model_costs_usd).length > 0 ? (
                  <CostComparisonGrid
                    title="LLM cost comparison across models"
                    subtitle="Re-prices this session's actual token counts against other models' rates. Only the model marked “Actual” ran this session — every other figure is an estimate, since a different provider's tokenizer would not produce the same token counts for the same conversation."
                    costs={selectedRecord.session_llm_model_costs_usd}
                    providerSuffix="LLM"
                    actualModel={selectedRecord.session_config?.llm_model ?? null}
                  />
                ) : null}

                <div className="my-8 border-t border-line" />
              </>
            ) : null}

            <SectionHeader label="STT" />
            <div className="mb-5 grid grid-cols-2 gap-4">
              <MetricCard label="Turns" value={String(selectedRecord.turn_count)} sub="captured user turns" />
              <MetricCard label="STT Duration" value={formatDuration(selectedRecord.session_stt_duration_sec)} sub="session STT duration" />
            </div>

            {selectedRecord.session_stt_latency_ms ? (
              <div className="mb-5 grid grid-cols-2 gap-4">
                <MetricCard
                  label="STT Latency — median"
                  value={formatLatency(selectedRecord.session_stt_latency_ms.median_ms)}
                  sub={`${titleCase(selectedRecord.session_stt_latency_ms.provider)} · speech → final`}
                />
                <MetricCard
                  label="STT Latency — p95"
                  value={formatLatency(selectedRecord.session_stt_latency_ms.p95_ms)}
                  sub={`${selectedRecord.session_stt_latency_ms.count} samples`}
                />
              </div>
            ) : null}

            <CostComparisonGrid
              title="Cost comparision across models"
              subtitle="Computed from this audio session’s captured duration. No extra provider calls required."
              costs={selectedRecord.session_model_costs_usd}
              providerSuffix="STT"
            />

            {selectedRecord.session_tts_sent_characters != null ||
            selectedRecord.session_tts_latency_ms ||
            (selectedRecord.session_tts_model_costs_usd &&
              Object.keys(selectedRecord.session_tts_model_costs_usd).length > 0) ? (
              <>
                <div className="my-8 border-t border-line" />
                <SectionHeader label="TTS" />
                {selectedRecord.session_tts_sent_characters != null ? (
                  <div className="mb-5 grid grid-cols-4 gap-4">
                    <MetricCard
                      label="TTS Characters"
                      value={selectedRecord.session_tts_sent_characters.toLocaleString()}
                      sub="characters sent to provider"
                    />
                  </div>
                ) : null}
                {selectedRecord.session_tts_latency_ms ? (
                  <div className="mb-5 grid grid-cols-2 gap-4">
                    <MetricCard
                      label="TTS Latency — median"
                      value={formatLatency(selectedRecord.session_tts_latency_ms.median_ms)}
                      sub={`${titleCase(selectedRecord.session_tts_latency_ms.provider)} · text → first audio`}
                    />
                    <MetricCard
                      label="TTS Latency — p95"
                      value={formatLatency(selectedRecord.session_tts_latency_ms.p95_ms)}
                      sub={`${selectedRecord.session_tts_latency_ms.count} samples`}
                    />
                  </div>
                ) : null}
                {selectedRecord.session_tts_model_costs_usd &&
                Object.keys(selectedRecord.session_tts_model_costs_usd).length > 0 ? (
                  <CostComparisonGrid
                    title="TTS cost comparison across models"
                    subtitle="Computed from characters sent to the TTS provider this session. Cross-provider figures are estimates - normalization differs per provider."
                    costs={selectedRecord.session_tts_model_costs_usd}
                    providerSuffix="TTS"
                  />
                ) : null}
              </>
            ) : null}
          </>
        ) : null}
      </section>
    </div>
  );
}

function CostComparisonGrid({
  title,
  subtitle,
  costs,
  providerSuffix,
  actualModel,
}: {
  title: string;
  subtitle: string;
  costs: Record<string, Record<string, number>>;
  providerSuffix: string;
  actualModel?: string | null;
}) {
  const allEntries = Object.entries(costs).flatMap(([provider, models]) =>
    Object.entries(models).map(([model, cost]) => ({ provider, model, cost })),
  );
  const rankedAll = [...allEntries].sort((a, b) => a.cost - b.cost);
  const globalLowest = rankedAll[0] ?? null;
  const globalHighest = rankedAll[rankedAll.length - 1] ?? null;
  const hasSpread = rankedAll.length > 1;
  return (
    <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        <p className="mt-1 text-xs text-faint">{subtitle}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {Object.entries(costs).map(([provider, models]) => (
          <div key={provider} className="rounded-xl border border-line bg-off p-4">
            <div className="mb-3 text-sm font-semibold text-text">
              {titleCase(provider)} {providerSuffix}
            </div>
            <div className="space-y-2 text-xs">
              {Object.entries(models).map(([model, cost]) => {
                const isHighest = hasSpread && globalHighest?.provider === provider && globalHighest?.model === model;
                const isLowest = hasSpread && globalLowest?.provider === provider && globalLowest?.model === model;
                const isActual = Boolean(actualModel) && model === actualModel;
                return (
                  <div key={model} className="flex items-center justify-between gap-3 rounded-lg bg-white px-3 py-2">
                    <div className="min-w-0">
                      <div className="font-medium text-muted">{model}</div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {isActual ? (
                          <span className="rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700">Actual</span>
                        ) : actualModel ? (
                          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">Estimate</span>
                        ) : null}
                        {isHighest ? (
                          <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700">Highest</span>
                        ) : null}
                        {isLowest ? (
                          <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">Lowest</span>
                        ) : null}
                      </div>
                    </div>
                    <span className="font-mono text-text">{isActual ? '$' : '~$'}{cost.toFixed(6)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SessionConfigStrip({ config }: { config?: SessionConfigInfo | null }) {
  if (!config) return null;
  const sttLabel = [config.stt_provider, config.stt_model].filter(Boolean).join(' · ');
  const llmLabel = config.llm_model ?? null;
  const ttsLabel = [config.tts_provider, config.tts_model ?? config.tts_voice].filter(Boolean).join(' · ');
  const pills: { key: string; label: string; value: string }[] = [];
  if (sttLabel) pills.push({ key: 'stt', label: 'STT', value: sttLabel });
  if (llmLabel) pills.push({ key: 'llm', label: 'LLM', value: llmLabel });
  if (ttsLabel) pills.push({ key: 'tts', label: 'TTS', value: ttsLabel });
  if (pills.length === 0) return null;
  return (
    <div className="mb-5 flex flex-wrap gap-2">
      {pills.map((pill) => (
        <div
          key={pill.key}
          className="flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1.5 text-xs shadow-sm"
        >
          <span className="font-semibold uppercase tracking-wide text-faint">{pill.label}</span>
          <span className="text-text">{pill.value}</span>
        </div>
      ))}
    </div>
  );
}

function SectionHeader({ label }: { label: string }) {
  return (
    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-faint">{label}</h3>
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

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatDuration(seconds: number) {
  return `~${seconds.toFixed(2)}s`;
}

function formatLatency(value: number) {
  return `~${value.toFixed(1)} ms`;
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
          <span>Metrics</span>
        </div>
      ) : null}
      <div className="max-w-5xl rounded-lg border border-dashed border-line bg-white p-8 text-center">
        <div className="text-sm font-semibold text-text">{title}</div>
        <p className="mt-1 text-xs text-faint">{body}</p>
      </div>
    </div>
  );
}
