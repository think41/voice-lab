from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TraceEventRead(BaseModel):
    id: str
    sequence: int
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class LlmUsageSummary(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    source: str = "runtime"


class SttUsageSummary(BaseModel):
    audio_seconds: float = 0.0
    cost_usd: float = 0.0
    source: str = "runtime"


class TtsUsageSummary(BaseModel):
    characters: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    source: str = "runtime"


class UsageSummary(BaseModel):
    llm: LlmUsageSummary = Field(default_factory=LlmUsageSummary)
    stt: SttUsageSummary = Field(default_factory=SttUsageSummary)
    tts: TtsUsageSummary = Field(default_factory=TtsUsageSummary)
    total_cost_usd: float = 0.0


class ProviderTraceRead(BaseModel):
    provider: str = ""
    model: str = ""
    transport: str = ""
    voice: str | None = None
    provider_request_id: str | None = None
    provider_lookup_available: bool = False
    unavailable_reason: str | None = None
    provider_cost_usd: float | None = None
    method: str | None = None
    tier: str | None = None
    deployment: str | None = None
    provider_models: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)


class RunProviderSummary(BaseModel):
    stt: ProviderTraceRead = Field(default_factory=ProviderTraceRead)
    tts: ProviderTraceRead = Field(default_factory=ProviderTraceRead)


class RunRead(BaseModel):
    id: str
    agent_id: str
    adk_session_id: str
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    trace_events: list[TraceEventRead] = Field(default_factory=list)
    usage_summary: UsageSummary = Field(default_factory=UsageSummary)
    provider_summary: RunProviderSummary = Field(default_factory=RunProviderSummary)
