export type Provider = 'deepgram' | 'elevenlabs' | 'sarvam';

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
    source: string;
  };
  stt: {
    audio_seconds: number;
    cost_usd: number;
    source: string;
  };
  tts: {
    characters: number;
    cost_usd: number;
    avg_latency_ms: number;
    source: string;
  };
  total_cost_usd: number;
}

export interface ProviderTraceSummary {
  provider: string;
  model: string;
  transport: string;
  voice: string | null;
  provider_request_id: string | null;
  provider_lookup_available: boolean;
  unavailable_reason: string | null;
  provider_cost_usd: number | null;
  method: string | null;
  tier: string | null;
  deployment: string | null;
  provider_models: string[];
  features: string[];
}

export interface RunProviderSummary {
  stt: ProviderTraceSummary;
  tts: ProviderTraceSummary;
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
  provider_summary: RunProviderSummary;
}

export interface TextTurn {
  run_id: string;
  user_text: string;
  assistant_text: string;
}

export interface AudioProviderMetrics {
  call_count: number;
  success_count: number;
  error_count: number;
  latency_avg_ms: number;
  latency_median_ms: number;
  latency_p95_ms: number;
}

export interface AudioEvaluationRecord {
  session_id: string;
  run_id: string;
  adk_session_id: string;
  created_at: string;
  turn_count: number;
  session_stt_duration_sec: number;
  session_model_costs_usd: Record<string, Record<string, number>>;
  provider_session_metrics: Record<string, AudioProviderMetrics>;
  file_paths: string[];
  evaluate_mode: boolean;
}
