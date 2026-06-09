from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolConfig(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True


class AgentConfig(BaseModel):
    name: str = "Untitled Agent"
    model: str = "gemini-2.0-flash"
    instruction: str = "You are a helpful voice assistant."
    stt_provider: str = "deepgram"
    stt_model: str = "nova-2"
    tts_provider: str = "elevenlabs"
    tts_voice: str = "Rachel"
    temperature: float = Field(default=0.4, ge=0, le=2)
    first_message: str = "Hi, how can I help?"
    tools: list[ToolConfig] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentCreate(BaseModel):
    name: str
    config: AgentConfig


class AgentUpdate(BaseModel):
    name: str | None = None
    config: AgentConfig | None = None


class AgentRead(BaseModel):
    id: str
    name: str
    config: AgentConfig


class RuntimeStatus(BaseModel):
    status: Literal["ready", "missing_provider_config", "error"]
    detail: str
