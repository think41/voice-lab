import { Play, Rocket } from 'lucide-react';

import { Button } from '../ui/Button';
import { StatusPill } from '../ui/StatusPill';

interface TopBarProps {
  activeView: string;
  onViewChange: (view: 'builder' | 'runs' | 'reports') => void;
  onDeploy: () => void;
  onTestCall: () => void;
}

const tabs: Array<'builder' | 'runs' | 'reports'> = ['builder', 'runs', 'reports'];

export function TopBar({ activeView, onViewChange, onDeploy, onTestCall }: TopBarProps) {
  return (
    <header className="z-40 flex h-[52px] shrink-0 items-center bg-navy px-5 text-white">
      <div className="flex items-center gap-2.5 border-r border-white/10 pr-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-sm font-bold">V</div>
        <div>
          <div className="text-[15px] font-semibold leading-4">VoiceLab</div>
          <div className="text-[10px] uppercase tracking-wider text-white/40">by think41</div>
        </div>
      </div>
      <nav className="ml-5 flex h-full">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => onViewChange(tab)}
            className={`border-b-2 px-4 text-xs font-medium capitalize transition ${activeView === tab ? 'border-primary text-white' : 'border-transparent text-white/50 hover:text-white/80'}`}
          >
            {tab === 'runs' ? 'Test Runs' : tab}
          </button>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <StatusPill label="Pipecat ADK live" />
        <Button variant="ghost" icon={<Play size={14} />} onClick={onTestCall}>Test call</Button>
        <Button variant="primary" icon={<Rocket size={14} />} onClick={onDeploy}>Deploy</Button>
      </div>
    </header>
  );
}
