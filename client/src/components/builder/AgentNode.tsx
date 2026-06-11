import type { AgentConfig } from '../../lib/types';

interface AgentNodeProps {
  config: AgentConfig;
  selected: boolean;
  onSelect: () => void;
}

export function AgentNode({ config, selected, onSelect }: AgentNodeProps) {
  return (
    <button
      className={`absolute left-[120px] top-[150px] w-[230px] rounded-xl border bg-white text-left shadow-soft transition hover:border-primary hover:shadow-panel ${selected ? 'border-primary ring-4 ring-blue-100' : 'border-line'}`}
      onClick={onSelect}
    >
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-primary" />
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-text">{config.name}</span>
        <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[9px] font-semibold text-primary">root</span>
      </div>
      <div className="space-y-1.5 px-3 py-2.5 text-[10px]">
        <div className="flex justify-between gap-3"><span className="text-faint">LLM</span><span className="truncate font-mono text-muted">{config.model}</span></div>
        <div className="flex justify-between gap-3"><span className="text-faint">STT</span><span className="truncate font-mono text-muted">{config.stt_provider}/{config.stt_model}</span></div>
        <div className="flex justify-between gap-3"><span className="text-faint">TTS</span><span className="truncate font-mono text-muted">{config.tts_provider}</span></div>
        <div className="flex flex-wrap gap-1 pt-1">
          {config.tools.filter((tool) => tool.enabled).slice(0, 3).map((tool) => (
            <span key={tool.name} className="rounded border border-line bg-off px-1.5 py-0.5 font-mono text-[9px] text-faint">{tool.name}</span>
          ))}
        </div>
      </div>
      <span className="absolute -right-1.5 top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-line bg-white" />
    </button>
  );
}
