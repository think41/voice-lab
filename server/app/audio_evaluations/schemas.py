from pydantic import BaseModel, Field


class LiveLatencyRead(BaseModel):
    provider: str
    model: str
    count: int
    median_ms: float
    p95_ms: float


class SessionConfigRead(BaseModel):
    stt_provider: str | None = None
    stt_model: str | None = None
    llm_model: str | None = None
    tts_provider: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None


class AudioEvaluationRead(BaseModel):
    session_id: str
    run_id: str
    adk_session_id: str
    created_at: str
    turn_count: int
    session_stt_duration_sec: float
    streamed_seconds: float
    stt_cost_usd: float | None = None
    session_model_costs_usd: dict[str, dict[str, float]]
    session_llm_prompt_tokens: int = 0
    session_llm_completion_tokens: int = 0
    session_llm_total_tokens: int = 0
    session_llm_cost_usd: float | None = None
    session_llm_model_costs_usd: dict[str, dict[str, float]] = Field(default_factory=dict)
    file_paths: list[str]
    session_tts_sent_characters: int | None = None
    session_tts_model_costs_usd: dict[str, dict[str, float]] = Field(default_factory=dict)
    session_stt_latency_ms: LiveLatencyRead | None = None
    session_tts_latency_ms: LiveLatencyRead | None = None
    session_config: SessionConfigRead | None = None
