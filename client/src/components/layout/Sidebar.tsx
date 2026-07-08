import { Activity, Bot, Headphones, Plus, Settings, Sliders, TrendingUp } from 'lucide-react';

import type { AgentRecord } from '../../lib/types';

type View = 'builder' | 'runs' | 'audio' | 'reports' | 'settings';

interface SidebarProps {
  agents: AgentRecord[];
  selectedAgentId: string | null;
  activeView: View;
  onSelectAgent: (id: string) => void;
  onNewAgent: () => void;
  onViewChange: (view: View) => void;
}

const subItems: Array<{ view: View; label: string; icon: typeof Sliders }> = [
  { view: 'builder', label: 'Builder', icon: Sliders },
  { view: 'runs', label: 'Conversations', icon: Activity },
  { view: 'audio', label: 'Audio', icon: Headphones },
  { view: 'reports', label: 'Reports', icon: TrendingUp },
];

export function Sidebar({
  agents,
  selectedAgentId,
  activeView,
  onSelectAgent,
  onNewAgent,
  onViewChange,
}: SidebarProps) {
  return (
    <aside className="flex w-[220px] shrink-0 flex-col overflow-y-auto border-r border-line bg-white">
      <section className="px-2.5 pb-2 pt-3.5">
        <div className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-faint">
          Agents
        </div>
        {agents.map((agent) => {
          const selected = agent.id === selectedAgentId;
          return (
            <div key={agent.id}>
              <button
                onClick={() => onSelectAgent(agent.id)}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-xs font-medium ${
                  selected ? 'bg-blue-50 text-primary' : 'text-muted hover:bg-off hover:text-text'
                }`}
              >
                <Bot size={15} />
                <span className="truncate">{agent.name}</span>
              </button>
              {selected ? (
                <div className="ml-3 mt-0.5 border-l border-line pl-2">
                  {subItems.map(({ view, label, icon: Icon }) => {
                    const active = activeView === view;
                    return (
                      <button
                        key={view}
                        onClick={() => onViewChange(view)}
                        className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[11px] font-medium ${
                          active
                            ? 'bg-blue-50 text-primary'
                            : 'text-muted hover:bg-off hover:text-text'
                        }`}
                      >
                        <Icon size={13} />
                        <span className="truncate">{label}</span>
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
        <button
          className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs italic text-faint hover:bg-off"
          onClick={onNewAgent}
        >
          <Plus size={15} /> New agent
        </button>
      </section>
      <div className="mt-auto border-t border-line p-2.5">
        <button
          className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs font-medium ${
            activeView === 'settings' ? 'bg-blue-50 text-primary' : 'text-muted hover:bg-off'
          }`}
          onClick={() => onViewChange('settings')}
        >
          <Settings size={15} /> Settings
        </button>
      </div>
    </aside>
  );
}
