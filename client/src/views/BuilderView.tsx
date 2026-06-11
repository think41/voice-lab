import { Save } from 'lucide-react';
import { useState } from 'react';

import { AgentCanvas } from '../components/builder/AgentCanvas';
import { AgentInspector } from '../components/builder/AgentInspector';
import { AgentJsonEditor } from '../components/builder/AgentJsonEditor';
import { AgentPalette } from '../components/builder/AgentPalette';
import { Button } from '../components/ui/Button';
import { Tabs } from '../components/ui/Tabs';
import type { AgentConfig } from '../lib/types';

type BuilderMode = 'canvas' | 'json';

interface BuilderViewProps {
  config: AgentConfig;
  onConfigChange: (config: AgentConfig) => void;
  onSave: () => void;
}

export function BuilderView({ config, onConfigChange, onSave }: BuilderViewProps) {
  const [mode, setMode] = useState<BuilderMode>('canvas');
  const [inspectorOpen, setInspectorOpen] = useState(true);

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-11 shrink-0 items-center gap-2 border-b border-line bg-white px-4">
          <span className="text-xs font-semibold">{config.name}</span>
          <span className="text-[11px] text-faint">- single UI-configured root agent</span>
          <div className="h-4 w-px bg-line" />
          <Tabs value={mode} options={['canvas', 'json']} onChange={setMode} />
          <div className="ml-auto flex items-center gap-2">
            <span className="text-[11px] text-faint">Click the agent to configure</span>
            <Button icon={<Save size={14} />} variant="primary" onClick={onSave}>Save config</Button>
          </div>
        </div>
        {mode === 'canvas' ? (
          <AgentCanvas config={config} selected={inspectorOpen} onSelect={() => setInspectorOpen(true)} />
        ) : (
          <AgentJsonEditor config={config} onChange={onConfigChange} />
        )}
      </div>
      <div className="hidden w-[200px] border-l border-line bg-white xl:block"><AgentPalette /></div>
      {inspectorOpen ? <AgentInspector config={config} onChange={onConfigChange} onSave={onSave} onClose={() => setInspectorOpen(false)} /> : null}
    </div>
  );
}
