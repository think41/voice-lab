import { Activity, Bot, Plus, Settings, TrendingUp } from 'lucide-react';

import type { AgentRecord } from '../../lib/types';

interface SidebarProps {
  agents: AgentRecord[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string) => void;
  onNewAgent: () => void;
  onViewChange: (view: 'runs' | 'reports' | 'settings') => void;
}

export function Sidebar({ agents, selectedAgentId, onSelectAgent, onNewAgent, onViewChange }: SidebarProps) {
  return (
    <aside className="flex w-[200px] shrink-0 flex-col overflow-y-auto border-r border-line bg-white">
      <section className="px-2.5 pb-1.5 pt-3.5">
        <div className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-faint">Agents</div>
        {agents.map((agent) => (
          <button
            key={agent.id}
            onClick={() => onSelectAgent(agent.id)}
            className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-xs font-medium ${agent.id === selectedAgentId ? 'bg-blue-50 text-primary' : 'text-muted hover:bg-off hover:text-text'}`}
          >
            <Bot size={15} />
            <span className="truncate">{agent.name}</span>
            <span className="ml-auto rounded-full bg-off2 px-1.5 text-[10px] text-faint">1</span>
          </button>
        ))}
        <button className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs italic text-faint hover:bg-off" onClick={onNewAgent}>
          <Plus size={15} /> New agent
        </button>
      </section>
      <section className="px-2.5 pb-1.5 pt-3.5">
        <div className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-faint">Runs</div>
        <button className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs font-medium text-muted hover:bg-off" onClick={() => onViewChange('runs')}>
          <Activity size={15} /> Recent runs
        </button>
        <button className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs font-medium text-muted hover:bg-off" onClick={() => onViewChange('reports')}>
          <TrendingUp size={15} /> Reports
        </button>
      </section>
      <div className="mt-auto border-t border-line p-2.5">
        <button className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs font-medium text-muted hover:bg-off" onClick={() => onViewChange('settings')}>
          <Settings size={15} /> Settings
        </button>
      </div>
    </aside>
  );
}
