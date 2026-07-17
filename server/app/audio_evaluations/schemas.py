from pydantic import BaseModel


class AudioProviderMetricsRead(BaseModel):
    call_count: int
    success_count: int
    error_count: int
    latency_avg_ms: float
    latency_median_ms: float
    latency_p95_ms: float


class AudioEvaluationRead(BaseModel):
    session_id: str
    run_id: str
    adk_session_id: str
    created_at: str
    turn_count: int
    session_stt_duration_sec: float
    session_model_costs_usd: dict[str, dict[str, float]]
    provider_session_metrics: dict[str, AudioProviderMetricsRead]
    file_paths: list[str]
    evaluate_mode: bool
