from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
}
DEFAULT_MODEL = "gemini-2.5-flash"
SUPPORTED_STT_PROVIDERS = {"deepgram", "elevenlabs"}
SUPPORTED_TTS_PROVIDERS = {"deepgram", "elevenlabs"}
DEFAULT_STT_PROVIDER = "deepgram"
DEFAULT_TTS_PROVIDER = "deepgram"
DEFAULT_STT_MODEL_BY_PROVIDER = {
    "deepgram": "nova-2",
    "elevenlabs": "scribe_v2_realtime",
}
DEFAULT_TTS_VOICE_BY_PROVIDER = {
    "deepgram": "aura-asteria-en",
    "elevenlabs": "JBFqnCBsd6RMkjVDRZzb",
}
DEFAULT_TTS_MODEL_BY_PROVIDER = {
    "deepgram": "aura-asteria-en",
    "elevenlabs": "eleven_turbo_v2_5",
}
SUPPORTED_STT_MODELS = {
    "deepgram": {"nova-2"},
    "elevenlabs": {"scribe_v2_realtime"},
}
SUPPORTED_DEEPGRAM_VOICES = {
    "aura-asteria-en",
    "aura-luna-en",
    "aura-stella-en",
    "aura-athena-en",
    "aura-2-thalia-en",
    "aura-2-orion-en",
    "aura-2-vesta-en",
    "aura-2-zeus-en",
}
LEGACY_DEEPGRAM_VOICES = {"Rachel": "aura-asteria-en"}


class ToolConfig(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True


class AgentConfig(BaseModel):
    name: str = "Untitled Agent"
    model: str = DEFAULT_MODEL
    instruction: str = "You are a helpful voice assistant."
    stt_provider: str = DEFAULT_STT_PROVIDER
    stt_model: str = DEFAULT_STT_MODEL_BY_PROVIDER[DEFAULT_STT_PROVIDER]
    tts_provider: str = DEFAULT_TTS_PROVIDER
    tts_voice: str = DEFAULT_TTS_VOICE_BY_PROVIDER[DEFAULT_TTS_PROVIDER]
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

    @model_validator(mode="after")
    def normalize_speech_provider_config(self) -> "AgentConfig":
        if self.stt_provider not in SUPPORTED_STT_PROVIDERS:
            self.stt_provider = DEFAULT_STT_PROVIDER
        if self.tts_provider not in SUPPORTED_TTS_PROVIDERS:
            self.tts_provider = DEFAULT_TTS_PROVIDER

        supported_stt_models = SUPPORTED_STT_MODELS[self.stt_provider]
        if self.stt_model not in supported_stt_models:
            self.stt_model = DEFAULT_STT_MODEL_BY_PROVIDER[self.stt_provider]

        if self.tts_provider == "deepgram":
            self.tts_voice = LEGACY_DEEPGRAM_VOICES.get(self.tts_voice, self.tts_voice)
            if self.tts_voice not in SUPPORTED_DEEPGRAM_VOICES:
                self.tts_voice = DEFAULT_TTS_VOICE_BY_PROVIDER["deepgram"]
        elif not isinstance(self.tts_voice, str) or not self.tts_voice.strip():
            self.tts_voice = DEFAULT_TTS_VOICE_BY_PROVIDER["elevenlabs"]

        return self


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
