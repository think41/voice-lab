import { useEffect, useState } from 'react';

import type { AgentConfig } from '../../lib/types';
import { Button } from '../ui/Button';

interface AgentJsonEditorProps {
  config: AgentConfig;
  onChange: (config: AgentConfig) => void;
}

export function AgentJsonEditor({ config, onChange }: AgentJsonEditorProps) {
  const [value, setValue] = useState(JSON.stringify(config, null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setValue(JSON.stringify(config, null, 2));
  }, [config]);

  const apply = () => {
    try {
      onChange(JSON.parse(value) as AgentConfig);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid JSON');
    }
  };

  return (
    <div className="flex flex-1 flex-col bg-off p-5">
      <textarea className="min-h-0 flex-1 resize-none rounded-lg border border-line bg-white p-4 font-mono text-[11px] leading-5 outline-none" value={value} onChange={(event) => setValue(event.target.value)} />
      <div className="mt-3 flex items-center justify-between">
        <span className="text-xs text-danger">{error}</span>
        <Button variant="primary" onClick={apply}>Apply JSON</Button>
      </div>
    </div>
  );
}
