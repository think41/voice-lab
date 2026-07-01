from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SUPPORTED_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
}
DEFAULT_MODEL = "gemini-2.5-flash"


class ToolConfig(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True


class AgentConfig(BaseModel):
    name: str = "Untitled Agent"
    model: str = DEFAULT_MODEL
    instruction: str = "You are a helpful voice assistant."
    stt_provider: str = "deepgram"
    stt_model: str = "nova-2"
    tts_provider: str = "deepgram"
    tts_voice: str = "aura-asteria-en"
    temperature: float = Field(default=0.4, ge=0, le=2)
    first_message: str = "Hi, how can I help?"
    tools: list[ToolConfig] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model", mode="before")
    @classmethod
    def normalize_unsupported_model(cls, value: Any) -> str:
        if not isinstance(value, str) or value not in SUPPORTED_MODELS:
            return DEFAULT_MODEL
        return value


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
