import { Play, Rocket } from 'lucide-react';

import { Button } from '../ui/Button';
import { StatusPill } from '../ui/StatusPill';

interface TopBarProps {
  onDeploy: () => void;
  onTestCall: () => void;
}

export function TopBar({ onDeploy, onTestCall }: TopBarProps) {
  return (
    <header className="z-40 flex h-[52px] shrink-0 items-center bg-navy px-5 text-white">
      <div className="flex items-center gap-2.5 pr-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-sm font-bold">V</div>
        <div>
          <div className="text-[15px] font-semibold leading-4">VoiceLab</div>
          <div className="text-[10px] uppercase tracking-wider text-white/40">by think41</div>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <Button variant="ghost" icon={<Play size={14} />} onClick={onTestCall}>Test call</Button>
        {/* <Button variant="primary" icon={<Rocket size={14} />} onClick={onDeploy}>Deploy</Button> */}
      </div>
    </header>
  );
}
