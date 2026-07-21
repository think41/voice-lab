from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TraceEventRead(BaseModel):
    id: str
    sequence: int
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RunRead(BaseModel):
    id: str
    agent_id: str
    adk_session_id: str
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    trace_events: list[TraceEventRead] = Field(default_factory=list)
