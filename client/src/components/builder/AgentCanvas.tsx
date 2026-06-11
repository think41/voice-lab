import type { AgentConfig } from '../../lib/types';

import { AgentNode } from './AgentNode';

interface AgentCanvasProps {
  config: AgentConfig;
  selected: boolean;
  onSelect: () => void;
}

export function AgentCanvas({ config, selected, onSelect }: AgentCanvasProps) {
  return (
    <div className="canvas-grid relative flex-1 overflow-hidden">
      <svg className="pointer-events-none absolute inset-0 h-full w-full">
        <path d="M350 220 C430 220 450 120 530 120" fill="none" stroke="#C4CCDF" strokeWidth="2" />
      </svg>
      <AgentNode config={config} selected={selected} onSelect={onSelect} />
      <div className="absolute left-[530px] top-[72px] w-[210px] rounded-xl border border-dashed border-line bg-white/70 px-4 py-6 text-center text-xs text-faint">
        Add sub-agents later. V1 runs the selected root agent.
      </div>
    </div>
  );
}
