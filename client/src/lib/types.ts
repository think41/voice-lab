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

export interface RunRecord {
  id: string;
  agent_id: string;
  adk_session_id: string;
  status: string;
  summary: Record<string, unknown>;
  created_at: string;
  trace_events: TraceEvent[];
}

export interface TextTurn {
  run_id: string;
  user_text: string;
  assistant_text: string;
}

export interface TtsVoiceOption {
  voice_id: string;
  label: string;
  provider: 'deepgram' | 'elevenlabs';
  sample: string | null;
  accent: string | null;
}

export interface ProviderCatalog {
  tts: TtsVoiceOption[];
}

export interface LiveLatencyMetrics {
  provider: string;
  model: string;
  count: number;
  median_ms: number;
  p95_ms: number;
}

export interface SessionConfigInfo {
  stt_provider?: string | null;
  stt_model?: string | null;
  llm_model?: string | null;
  tts_provider?: string | null;
  tts_model?: string | null;
  tts_voice?: string | null;
}

export interface AudioEvaluationRecord {
  session_id: string;
  run_id: string;
  adk_session_id: string;
  created_at: string;
  turn_count: number;
  session_stt_duration_sec: number;
  streamed_seconds: number;
  stt_cost_usd: number | null;
  session_model_costs_usd: Record<string, Record<string, number>>;
  session_llm_prompt_tokens: number;
  session_llm_completion_tokens: number;
  session_llm_total_tokens: number;
  session_llm_cost_usd: number | null;
  session_llm_model_costs_usd: Record<string, Record<string, number>>;
  file_paths: string[];
  session_tts_sent_characters?: number | null;
  session_tts_model_costs_usd?: Record<string, Record<string, number>>;
  session_stt_latency_ms?: LiveLatencyMetrics | null;
  session_tts_latency_ms?: LiveLatencyMetrics | null;
  session_config?: SessionConfigInfo | null;
}
