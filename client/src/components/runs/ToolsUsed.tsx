import type { RunRecord } from '../../lib/types';

/**
 * Shows tool invocations captured for a run. Backend capture of ADK
 * function-call events isn't shipped yet, so this reads any trace event
 * whose type begins with `tool.` — today that's always empty, and the
 * component populates automatically once the capture lands.
 */
export function ToolsUsed({ run }: { run: RunRecord | null }) {
  const toolEvents = run?.trace_events.filter((e) => e.event_type.startsWith('tool.')) ?? [];

  return (
    <section className="border-b border-line bg-white px-4 py-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[12px] font-semibold text-text">Tools used</h2>
        <span className="text-[10px] text-faint">{toolEvents.length} invocation{toolEvents.length === 1 ? '' : 's'}</span>
      </div>
      {toolEvents.length === 0 ? (
        <div className="mt-2 text-xs text-faint">No tool activity in this run.</div>
      ) : (
        <ul className="mt-2 space-y-1">
          {toolEvents.map((event) => (
            <li key={event.id} className="flex items-center gap-2 text-[11px] text-muted">
              <span className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] text-primary">
                {event.event_type}
              </span>
              <span className="truncate font-mono text-faint">
                {formatToolPayload(event.payload)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function formatToolPayload(payload: Record<string, unknown>): string {
  const name = typeof payload.name === 'string' ? payload.name : null;
  const args = payload.args ?? payload.arguments;
  if (name && args) return `${name}(${JSON.stringify(args)})`;
  if (name) return name;
  return JSON.stringify(payload);
}
