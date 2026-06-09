from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://voicelab:voicelab@localhost:5432/voicelab"
    adk_database_url: str = "postgresql+asyncpg://voicelab:voicelab@localhost:5432/voicelab"
    gemini_api_key: str | None = None
    stt_provider: str = "deepgram"
    stt_api_key: str | None = None
    tts_provider: str = "elevenlabs"
    tts_api_key: str | None = None
    elevenlabs_voice_id_rachel: str = "21m00Tcm4TlvDq8ikWAM"
    cors_origins_raw: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
