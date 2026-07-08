import { useEffect, useMemo, useState } from 'react';

import { TopBar } from './components/layout/TopBar';
import { Sidebar } from './components/layout/Sidebar';
import { Workspace } from './components/layout/Workspace';
import { Modal } from './components/ui/Modal';
import { Toast } from './components/ui/Toast';
import { TestCallPanel } from './components/test-call/TestCallPanel';
import { defaultAgentConfig } from './data/defaults';
import { normalizeSpeechConfig } from './data/providerOptions';
import { createAgent, isAbortError, listAgents, listRuns, updateAgent } from './lib/api';
import type { AgentConfig, AgentRecord, RunRecord } from './lib/types';
import type { AudioEvaluationRecord } from './lib/types';
import { BuilderView } from './views/BuilderView';
import { AudioView } from './views/AudioView';
import { ReportsView } from './views/ReportsView';
import { RunsView } from './views/RunsView';
import { SettingsView } from './views/SettingsView';
import { listAudioEvaluations } from './lib/api';

type View = 'builder' | 'runs' | 'audio' | 'reports' | 'settings';
const supportedModels = new Set(['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.5-flash-lite']);

function normalizeVoiceConfig(config: AgentConfig): AgentConfig {
  return normalizeSpeechConfig({
    ...config,
    model: supportedModels.has(config.model) ? config.model : 'gemini-2.5-flash',
  });
}

export default function App() {
  const [view, setView] = useState<View>('builder');
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [draftConfig, setDraftConfig] = useState<AgentConfig>(defaultAgentConfig);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [audioEvaluations, setAudioEvaluations] = useState<AudioEvaluationRecord[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [deployOpen, setDeployOpen] = useState(false);
  const [testCallOpen, setTestCallOpen] = useState(false);

  const selectedAgent = useMemo(() => agents.find((agent) => agent.id === selectedAgentId) ?? null, [agents, selectedAgentId]);
  const agentRuns = useMemo(
    () => (selectedAgentId ? runs.filter((run) => run.agent_id === selectedAgentId) : []),
    [runs, selectedAgentId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void refreshAgents(controller.signal);
    void refreshRuns(controller.signal);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (selectedAgent) setDraftConfig(normalizeVoiceConfig(selectedAgent.config));
  }, [selectedAgent]);

  useEffect(() => {
    const controller = new AbortController();
    if (!selectedAgentId) {
      setAudioEvaluations([]);
      return () => controller.abort();
    }
    void refreshAudioEvaluations(selectedAgentId, controller.signal);
    return () => controller.abort();
  }, [selectedAgentId]);

  useEffect(() => {
    setTestCallOpen(false);
  }, [selectedAgentId]);

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 2200);
  };

  const refreshAgents = async (signal?: AbortSignal) => {
    try {
      const records = await listAgents(signal);
      setAgents(records);
      if (records[0] && !selectedAgentId) setSelectedAgentId(records[0].id);
    } catch (error) {
      if (isAbortError(error)) return;
      setAgents([]);
    }
  };

  const refreshRuns = async (signal?: AbortSignal) => {
    try {
      setRuns(await listRuns(signal));
    } catch (error) {
      if (isAbortError(error)) return;
      setRuns([]);
    }
  };

  const refreshAudioEvaluations = async (agentId: string, signal?: AbortSignal) => {
    try {
      setAudioEvaluations(await listAudioEvaluations(agentId, signal));
    } catch (error) {
      if (isAbortError(error)) return;
      setAudioEvaluations([]);
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
      <TopBar onDeploy={() => setDeployOpen(true)} onTestCall={() => setTestCallOpen(true)} />
      <Workspace>
        <Sidebar
          agents={agents}
          selectedAgentId={selectedAgentId}
          onSelectAgent={setSelectedAgentId}
          onNewAgent={newAgent}
          onViewChange={setView}
          activeView={view}
        />
        {view === 'builder' ? <BuilderView config={draftConfig} onConfigChange={setDraftConfig} onSave={saveConfig} /> : null}
        {view === 'runs' ? <RunsView runs={agentRuns} agent={selectedAgent} /> : null}
        {view === 'audio' ? <AudioView records={audioEvaluations} agent={selectedAgent} /> : null}
        {view === 'reports' ? <ReportsView runs={agentRuns} agent={selectedAgent} /> : null}
        {view === 'settings' ? <SettingsView /> : null}
      </Workspace>
      <TestCallPanel
        agentId={selectedAgentId}
        open={testCallOpen}
        onClose={() => setTestCallOpen(false)}
        onSessionUpdated={() => {
          void refreshRuns();
          if (selectedAgentId) void refreshAudioEvaluations(selectedAgentId);
        }}
      />
      <Modal open={deployOpen} title="Deploy VoiceLab agent" subtitle="Deployment execution is intentionally outside the first implementation pass." onClose={() => setDeployOpen(false)} />
      <Toast message={toast} />
    </div>
  );
}
