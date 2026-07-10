import type { RunRecord, TraceEvent } from '../../lib/types';

const CONVERSATION_EVENT_TYPES = new Set(['transcript.final', 'agent.text']);

export function TraceTable({ run }: { run: RunRecord | null }) {
  const events = run?.trace_events ?? [];
  const conversationEvents = events.filter((event) => CONVERSATION_EVENT_TYPES.has(event.event_type));

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
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
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-xs text-faint">
                  No trace events captured yet.
                </td>
              </tr>
            ) : (
              events.map((event) => (
                <tr key={event.id} className="border-b border-line text-[11px] text-muted hover:bg-off">
                  <td className="px-3 py-2 font-mono text-faint">{String(event.sequence).padStart(2, '0')}</td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-blue-50 px-2 py-0.5 font-mono text-[10px] text-primary">
                      {event.event_type}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono">{formatPayload(event.payload)}</td>
                  <td className="px-3 py-2 font-mono text-faint">
                    {new Date(event.created_at).toLocaleTimeString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ConversationBubble({ event }: { event: TraceEvent }) {
  const role = event.payload.role === 'assistant' ? 'assistant' : 'user';
  const text = typeof event.payload.text === 'string' ? event.payload.text : '';
  return (
    <div className={`flex ${role === 'assistant' ? 'justify-start' : 'justify-end'}`}>
      <div
        className={`max-w-[74%] rounded-lg px-3 py-2 text-xs ${
          role === 'assistant' ? 'bg-off text-text' : 'bg-primary text-white'
        }`}
      >
        <div className={`mb-1 text-[9px] uppercase ${role === 'assistant' ? 'text-faint' : 'text-white/70'}`}>
          {role}
        </div>
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
