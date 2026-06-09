import type { AgentConfig, AgentRecord, RunRecord, TestSession } from './types';

const jsonHeaders = { 'Content-Type': 'application/json' };

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listAgents(): Promise<AgentRecord[]> {
  return request<AgentRecord[]>('/api/agents');
}

export async function createAgent(config: AgentConfig): Promise<AgentRecord> {
  return request<AgentRecord>('/api/agents', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ name: config.name, config })
  });
}

export async function updateAgent(agentId: string, config: AgentConfig): Promise<AgentRecord> {
  return request<AgentRecord>(`/api/agents/${agentId}`, {
    method: 'PUT',
    headers: jsonHeaders,
    body: JSON.stringify({ name: config.name, config })
  });
}

export async function listRuns(): Promise<RunRecord[]> {
  return request<RunRecord[]>('/api/runs');
}

export async function createTestSession(agentId: string): Promise<TestSession> {
  return request<TestSession>('/api/test-call/session', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ agent_id: agentId })
  });
}
