export type Provider = 'deepgram';

export interface ToolConfig {
  name: string;
  description: string;
  enabled: boolean;
}

export interface AgentConfig {
  name: string;
  model: string;
  instruction: string;
  stt_provider: string;
  stt_model: string;
  tts_provider: string;
  tts_voice: string;
  temperature: number;
  first_message: string;
  tools: ToolConfig[];
  metadata: Record<string, unknown>;
}

export interface AgentRecord {
  id: string;
  name: string;
  config: AgentConfig;
}

export interface TestSession {
  run_id: string;
  adk_session_id: string;
  websocket_url: string;
  first_message?: string;
}

export interface TraceEvent {
  id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface UsageSummary {
  llm: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
    avg_latency_ms: number;
  };
  stt: {
    audio_seconds: number;
    cost_usd: number;
    source?: 'derived' | 'provider';
  };
  tts: {
    characters: number;
    cost_usd: number;
    avg_latency_ms: number;
    source?: 'derived' | 'provider';
  };
  total_cost_usd: number;
}

export interface RunRecord {
  id: string;
  agent_id: string;
  adk_session_id: string;
  status: string;
  summary: Record<string, unknown>;
  created_at: string;
  trace_events: TraceEvent[];
  usage_summary: UsageSummary;
}

export interface TextTurn {
  run_id: string;
  user_text: string;
  assistant_text: string;
}

export interface DeepgramVoice {
  canonical_name: string;
  label: string;
  architecture: 'aura' | 'aura-2';
  languages: string[];
  accent: string | null;
  age: string | null;
  sample: string | null;
  image: string | null;
  tags: string[];
}

export interface DeepgramSttModel {
  canonical_name: string;
  label: string;
  architecture: 'nova-2' | 'nova-3';
  languages: string[];
  multilingual: boolean;
}

export interface DeepgramCatalog {
  tts: DeepgramVoice[];
  stt: DeepgramSttModel[];
}
