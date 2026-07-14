from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://voicelab:voicelab@localhost:5432/voicelab"
    adk_database_url: str = "postgresql+asyncpg://voicelab:voicelab@localhost:5432/voicelab"
    gemini_api_key: str | None = None
    deepgram_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    sarvam_api_key: str | None = None
    stt_provider: str = "deepgram"
    stt_api_key: str | None = None
    tts_provider: str = "deepgram"
    tts_api_key: str | None = None
    deepgram_management_api_key: str | None = None
    deepgram_project_id: str | None = None
    enable_stt_evaluation: bool = False
    enable_tts_evaluation: bool = False
    stt_evaluation_recordings_dir: str = "recordings"
    stt_evaluation_deepgram_model: str = "nova-3-monolingual"
    stt_evaluation_elevenlabs_model: str = "scribe_v2"
    stt_evaluation_sarvam_model: str = "saarika:v2.5"
    stt_evaluation_sarvam_url: str = "https://api.sarvam.ai/speech-to-text"
    cors_origins_raw: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
