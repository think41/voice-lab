from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Gemini models are bare IDs (resolved natively by ADK); all other providers use
# LiteLLM-prefixed IDs ("provider/model"), resolved via ADK's LiteLlm wrapper.
SUPPORTED_MODELS_BY_PROVIDER = {
    "gemini": {
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
    },
    "openai": {
        "openai/gpt-5.1",
        "openai/gpt-5-mini",
    },
    "anthropic": {
        "anthropic/claude-sonnet-5",
        "anthropic/claude-haiku-4-5",
        "anthropic/claude-opus-4-8",
    },
}
SUPPORTED_MODELS = set().union(*SUPPORTED_MODELS_BY_PROVIDER.values())
DEFAULT_MODEL = "gemini-3.5-flash"


def llm_provider_for_model(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return "gemini"
SUPPORTED_STT_PROVIDERS = {"deepgram", "elevenlabs"}
SUPPORTED_TTS_PROVIDERS = {"deepgram", "elevenlabs"}
DEFAULT_STT_PROVIDER = "deepgram"
DEFAULT_TTS_PROVIDER = "deepgram"
DEFAULT_STT_MODEL_BY_PROVIDER = {
    "deepgram": "nova-3",
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
    "deepgram": {"nova-3"},
    "elevenlabs": {"scribe_v2_realtime"},
}
LEGACY_DEEPGRAM_STT_MODELS = {
    "nova-3-monolingual": "nova-3",
    "nova-3-multilingual": "nova-3",
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

        if self.stt_provider == "deepgram":
            self.stt_model = LEGACY_DEEPGRAM_STT_MODELS.get(self.stt_model, self.stt_model)

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
