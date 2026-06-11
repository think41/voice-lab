import { useEffect, useMemo, useState } from 'react';

import { TopBar } from './components/layout/TopBar';
import { Sidebar } from './components/layout/Sidebar';
import { Workspace } from './components/layout/Workspace';
import { Modal } from './components/ui/Modal';
import { Toast } from './components/ui/Toast';
import { TestCallPanel } from './components/test-call/TestCallPanel';
import { defaultAgentConfig } from './data/defaults';
import { createAgent, listAgents, listRuns, updateAgent } from './lib/api';
import type { AgentConfig, AgentRecord, RunRecord } from './lib/types';
import { BuilderView } from './views/BuilderView';
import { ReportsView } from './views/ReportsView';
import { RunsView } from './views/RunsView';
import { SettingsView } from './views/SettingsView';

type View = 'builder' | 'runs' | 'reports' | 'settings';

function normalizeVoiceConfig(config: AgentConfig): AgentConfig {
  return {
    ...config,
    stt_provider: 'deepgram',
    tts_provider: 'deepgram',
    tts_voice: config.tts_voice === 'Rachel' ? 'aura-asteria-en' : config.tts_voice,
  };
}

export default function App() {
  const [view, setView] = useState<View>('builder');
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [draftConfig, setDraftConfig] = useState<AgentConfig>(defaultAgentConfig);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [deployOpen, setDeployOpen] = useState(false);
  const [testCallOpen, setTestCallOpen] = useState(false);

  const selectedAgent = useMemo(() => agents.find((agent) => agent.id === selectedAgentId) ?? null, [agents, selectedAgentId]);

  useEffect(() => {
    void refreshAgents();
    void refreshRuns();
  }, []);

  useEffect(() => {
    if (selectedAgent) setDraftConfig(normalizeVoiceConfig(selectedAgent.config));
  }, [selectedAgent]);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 2200);
  };

  const refreshAgents = async () => {
    try {
      const records = await listAgents();
      setAgents(records);
      if (records[0] && !selectedAgentId) setSelectedAgentId(records[0].id);
    } catch {
      setAgents([]);
    }
  };

  const refreshRuns = async () => {
    try {
      setRuns(await listRuns());
    } catch {
      setRuns([]);
    }
  };

  const saveConfig = async () => {
    try {
      const config = normalizeVoiceConfig(draftConfig);
      const saved = selectedAgentId ? await updateAgent(selectedAgentId, config) : await createAgent(config);
      setSelectedAgentId(saved.id);
      setAgents((current) => {
        const exists = current.some((agent) => agent.id === saved.id);
        return exists ? current.map((agent) => agent.id === saved.id ? saved : agent) : [...current, saved];
      });
      notify('Agent config saved');
    } catch (error) {
      notify(error instanceof Error ? error.message : 'Unable to save agent');
    }
  };

  const newAgent = () => {
    setSelectedAgentId(null);
    setDraftConfig({ ...defaultAgentConfig, name: 'Untitled Agent' });
    setView('builder');
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <TopBar activeView={view} onViewChange={setView} onDeploy={() => setDeployOpen(true)} onTestCall={() => setTestCallOpen(true)} />
      <Workspace>
        <Sidebar agents={agents} selectedAgentId={selectedAgentId} onSelectAgent={setSelectedAgentId} onNewAgent={newAgent} onViewChange={setView} />
        {view === 'builder' ? <BuilderView config={draftConfig} onConfigChange={setDraftConfig} onSave={saveConfig} /> : null}
        {view === 'runs' ? <RunsView runs={runs} /> : null}
        {view === 'reports' ? <ReportsView /> : null}
        {view === 'settings' ? <SettingsView /> : null}
      </Workspace>
      <TestCallPanel agentId={selectedAgentId} open={testCallOpen} onClose={() => setTestCallOpen(false)} onSessionUpdated={() => void refreshRuns()} />
      <Modal open={deployOpen} title="Deploy VoiceLab agent" subtitle="Deployment execution is intentionally outside the first implementation pass." onClose={() => setDeployOpen(false)} />
      <Toast message={toast} />
    </div>
  );
}
