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


class SttUsageSummary(BaseModel):
    audio_seconds: float = 0.0
    cost_usd: float = 0.0


class TtsUsageSummary(BaseModel):
    characters: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float = 0.0


class UsageSummary(BaseModel):
    llm: LlmUsageSummary = Field(default_factory=LlmUsageSummary)
    stt: SttUsageSummary = Field(default_factory=SttUsageSummary)
    tts: TtsUsageSummary = Field(default_factory=TtsUsageSummary)
    total_cost_usd: float = 0.0


class RunRead(BaseModel):
    id: str
    agent_id: str
    adk_session_id: str
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    trace_events: list[TraceEventRead] = Field(default_factory=list)
    usage_summary: UsageSummary = Field(default_factory=UsageSummary)
