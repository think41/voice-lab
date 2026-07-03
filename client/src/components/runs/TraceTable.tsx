import type { ProviderTraceSummary, RunRecord, TraceEvent } from '../../lib/types';

export function TraceTable({ run }: { run: RunRecord | null }) {
  const events = run?.trace_events ?? [];
  const conversationEvents = events.filter((event) => ['transcript.final', 'agent.text'].includes(event.event_type));

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <section className="border-b border-line bg-off px-4 py-3">
        <h2 className="text-[12px] font-semibold text-text">Provider Traceability</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <ProviderCard
            label="STT"
            provider={run?.provider_summary.stt ?? null}
            usageLine={run ? `${formatAudioSeconds(run.usage_summary.stt.audio_seconds)} audio` : null}
          />
          <ProviderCard
            label="TTS"
            provider={run?.provider_summary.tts ?? null}
            usageLine={run ? `${run.usage_summary.tts.characters} chars` : null}
          />
          <UsageCard run={run} />
        </div>
      </section>
      <section className="border-b border-line bg-white px-4 py-3">
        <h2 className="text-[12px] font-semibold text-text">Conversation</h2>
        <div className="mt-3 max-h-64 space-y-2 overflow-auto pr-1">
          {conversationEvents.length === 0 ? <div className="text-xs text-faint">No transcript captured yet.</div> : null}
          {conversationEvents.map((event) => (
            <ConversationBubble key={event.id} event={event} />
          ))}
        </div>
      </section>
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
                <td className="px-3 py-2 font-mono">{formatPayload(event.payload)}</td>
                <td className="px-3 py-2 font-mono text-faint">{new Date(event.created_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProviderCard({
  label,
  provider,
  usageLine,
}: {
  label: string;
  provider: ProviderTraceSummary | null;
  usageLine: string | null;
}) {
  if (!provider) {
    return <SummaryCard title={label} lines={['No provider data captured yet.']} tone="muted" />;
  }

  const title = [provider.provider || 'Unknown', provider.model || provider.voice || ''].filter(Boolean).join(' / ');
  const lines = [
    provider.transport ? `Transport: ${provider.transport}` : null,
    provider.voice ? `Voice: ${provider.voice}` : null,
    usageLine,
    provider.provider_request_id ? `Request ID: ${provider.provider_request_id}` : null,
    provider.provider_lookup_available
      ? 'Provider lookup available'
      : provider.unavailable_reason || 'Provider lookup unavailable',
  ].filter(Boolean) as string[];

  return (
    <SummaryCard
      title={label}
      subtitle={title || 'No provider data'}
      lines={lines}
      tone={provider.provider_lookup_available ? 'positive' : 'muted'}
    />
  );
}

function UsageCard({ run }: { run: RunRecord | null }) {
  if (!run) {
    return <SummaryCard title="Usage" lines={['No usage captured yet.']} tone="muted" />;
  }

  const { llm, total_cost_usd } = run.usage_summary;
  return (
    <SummaryCard
      title="Usage"
      subtitle={llm.total_tokens ? `${llm.total_tokens} LLM tokens` : 'No LLM usage yet'}
      lines={[
        `Prompt: ${llm.prompt_tokens}`,
        `Completion: ${llm.completion_tokens}`,
        `LLM latency: ${formatLatency(llm.avg_latency_ms)}`,
        `Estimated total cost: ${formatUsd(total_cost_usd)}`,
      ]}
      tone="muted"
    />
  );
}

function SummaryCard({
  title,
  subtitle,
  lines,
  tone,
}: {
  title: string;
  subtitle?: string;
  lines: string[];
  tone: 'positive' | 'muted';
}) {
  return (
    <div
      className={`rounded-lg border px-3 py-3 ${
        tone === 'positive' ? 'border-emerald-200 bg-emerald-50/50' : 'border-line bg-white'
      }`}
    >
      <div className="text-[10px] font-semibold uppercase tracking-wide text-faint">{title}</div>
      {subtitle ? <div className="mt-1 text-xs font-medium text-text">{subtitle}</div> : null}
      <div className="mt-2 space-y-1 text-[11px] text-muted">
        {lines.map((line) => (
          <div key={line}>{line}</div>
        ))}
      </div>
    </div>
  );
}

function ConversationBubble({ event }: { event: TraceEvent }) {
  const role = event.payload.role === 'assistant' ? 'assistant' : 'user';
  const text = typeof event.payload.text === 'string' ? event.payload.text : '';
  return (
    <div className={`flex ${role === 'assistant' ? 'justify-start' : 'justify-end'}`}>
      <div className={`max-w-[74%] rounded-lg px-3 py-2 text-xs ${role === 'assistant' ? 'bg-off text-text' : 'bg-primary text-white'}`}>
        <div className={`mb-1 text-[9px] uppercase ${role === 'assistant' ? 'text-faint' : 'text-white/70'}`}>{role}</div>
        <p className="leading-5">{text}</p>
      </div>
    </div>
  );
}

function formatPayload(payload: Record<string, unknown>) {
  if (typeof payload.text === 'string') return payload.text;
  if (typeof payload.message === 'string') return payload.message;
  return JSON.stringify(payload);
}

function formatAudioSeconds(value: number) {
  if (!value) return '0s';
  return `${value.toFixed(2)}s`;
}

function formatLatency(value: number) {
  if (!value) return '0 ms';
  return `${Math.round(value)} ms`;
}

function formatUsd(value: number) {
  return `$${value.toFixed(4)}`;
}
