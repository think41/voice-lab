import type { AgentConfig, AgentRecord, AudioEvaluationRecord, RunRecord, TestSession, TextTurn } from './types';

const jsonHeaders = { 'Content-Type': 'application/json' };

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listAgents(signal?: AbortSignal): Promise<AgentRecord[]> {
  return request<AgentRecord[]>('/api/agents', { signal });
}

export async function createAgent(config: AgentConfig, signal?: AbortSignal): Promise<AgentRecord> {
  return request<AgentRecord>('/api/agents', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ name: config.name, config }),
    signal,
  });
}

export async function updateAgent(
  agentId: string,
  config: AgentConfig,
  signal?: AbortSignal,
): Promise<AgentRecord> {
  return request<AgentRecord>(`/api/agents/${agentId}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify({ name: config.name, config }),
    signal,
  });
}

export async function listRuns(signal?: AbortSignal): Promise<RunRecord[]> {
  return request<RunRecord[]>('/api/runs', { signal });
}

export async function listAudioEvaluations(
  agentId: string,
  signal?: AbortSignal,
): Promise<AudioEvaluationRecord[]> {
  return request<AudioEvaluationRecord[]>(`/api/audio-evaluations/agent/${agentId}`, { signal });
}

export async function createTestSession(
  agentId: string,
  evaluateMode = false,
  signal?: AbortSignal,
): Promise<TestSession> {
  return request<TestSession>('/api/test-call/session', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ agent_id: agentId, evaluate_mode: evaluateMode }),
    signal,
  });
}


export async function createTextTurn(
  runId: string,
  message: string,
  signal?: AbortSignal,
): Promise<TextTurn> {
  return request<TextTurn>(`/api/test-call/session/${runId}/text`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ message }),
    signal,
  });
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
