import type { ReactNode } from 'react';

import { Plus, Trash2, X } from 'lucide-react';

import type { AgentConfig } from '../../lib/types';
import { Button } from '../ui/Button';

interface AgentInspectorProps {
  config: AgentConfig;
  onChange: (config: AgentConfig) => void;
  onSave: () => void;
  onClose: () => void;
}

export function AgentInspector({ config, onChange, onSave, onClose }: AgentInspectorProps) {
  const update = <K extends keyof AgentConfig>(key: K, value: AgentConfig[K]) => onChange({ ...config, [key]: value });
  const addTool = () => update('tools', [...config.tools, { name: 'new_tool', description: '', enabled: true }]);
  const updateTool = (index: number, name: string) => update('tools', config.tools.map((tool, i) => i === index ? { ...tool, name } : tool));
  const removeTool = (index: number) => update('tools', config.tools.filter((_, i) => i !== index));

  return (
    <aside className="flex w-[300px] shrink-0 flex-col border-l border-line bg-white">
      <div className="flex items-center justify-between border-b border-line px-4 py-3.5">
        <h2 className="text-[13px] font-semibold">Agent config</h2>
        <button className="rounded-md p-1 text-faint hover:bg-off hover:text-text" onClick={onClose}><X size={16} /></button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <Field label="Name"><input value={config.name} onChange={(event) => update('name', event.target.value)} /></Field>
        <Field label="Model"><input value={config.model} onChange={(event) => update('model', event.target.value)} /></Field>
        <Field label="Instruction"><textarea rows={5} value={config.instruction} onChange={(event) => update('instruction', event.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="STT"><input value={config.stt_provider} onChange={(event) => update('stt_provider', event.target.value)} /></Field>
          <Field label="STT model"><input value={config.stt_model} onChange={(event) => update('stt_model', event.target.value)} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="TTS"><input value={config.tts_provider} onChange={(event) => update('tts_provider', event.target.value)} /></Field>
          <Field label="Voice"><input value={config.tts_voice} onChange={(event) => update('tts_voice', event.target.value)} /></Field>
        </div>
        <Field label={`Temperature ${config.temperature.toFixed(1)}`}>
          <input type="range" min="0" max="2" step="0.1" value={config.temperature} onChange={(event) => update('temperature', Number(event.target.value))} />
        </Field>
        <Field label="First message"><textarea rows={3} value={config.first_message} onChange={(event) => update('first_message', event.target.value)} /></Field>
        <section>
          <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-faint">
            Tools
            <button className="text-primary" onClick={addTool}><Plus size={14} /></button>
          </div>
          <div className="space-y-1.5">
            {config.tools.map((tool, index) => (
              <div key={`${tool.name}-${index}`} className="flex items-center gap-1.5 rounded-md border border-line bg-off px-2 py-1.5">
                <input className="min-w-0 flex-1 bg-transparent font-mono text-[11px] outline-none" value={tool.name} onChange={(event) => updateTool(index, event.target.value)} />
                <button className="text-faint hover:text-danger" onClick={() => removeTool(index)}><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
        </section>
      </div>
      <div className="flex gap-2 border-t border-line p-3">
        <Button className="flex-1" variant="danger">Delete</Button>
        <Button className="flex-1" variant="primary" onClick={onSave}>Save</Button>
      </div>
    </aside>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-[11px] font-medium text-muted [&_input]:mt-1 [&_input]:w-full [&_input]:rounded-md [&_input]:border [&_input]:border-line [&_input]:px-2.5 [&_input]:py-2 [&_input]:text-xs [&_textarea]:mt-1 [&_textarea]:w-full [&_textarea]:resize-none [&_textarea]:rounded-md [&_textarea]:border [&_textarea]:border-line [&_textarea]:px-2.5 [&_textarea]:py-2 [&_textarea]:text-xs">
      {label}
      {children}
    </label>
  );
}
