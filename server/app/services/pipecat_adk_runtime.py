from base64 import b64encode
from collections.abc import AsyncIterator

import httpx
from google.adk.agents import Agent
from google.adk.apps import App

from app.core.config import get_settings
from app.schemas.agent import AgentConfig
from app.services.adk_session_service import create_adk_session_service
from app.services.voice_runtime import RuntimeEvent, VoiceRuntime


class PipecatAdkRuntime(VoiceRuntime):
    async def validate_environment(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required to run a voice test call")

    async def synthesize_first_message(self, config: AgentConfig) -> RuntimeEvent:
        settings = get_settings()
        if config.tts_provider != "elevenlabs":
            raise RuntimeError(f"Unsupported TTS provider: {config.tts_provider}")
        if not settings.tts_api_key:
            raise RuntimeError("TTS_API_KEY is required to speak the first message")

        voice_id = self._elevenlabs_voice_id(config.tts_voice)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "xi-api-key": settings.tts_api_key,
                },
                json={
                    "text": config.first_message,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
            )
            response.raise_for_status()

        return RuntimeEvent(
            type="audio.output",
            payload={
                "text": config.first_message,
                "mime_type": "audio/mpeg",
                "audio_base64": b64encode(response.content).decode("ascii"),
            },
        )

    def build_adk_app(self, config: AgentConfig) -> App:
        from pipecat_adk import AdkInterruptionPlugin

        agent = Agent(
            name=self._normalize_agent_name(config.name),
            model=config.model,
            instruction=config.instruction,
        )
        return App(name="voicelab", root_agent=agent, plugins=[AdkInterruptionPlugin()])

    async def run_test_call(
        self, config: AgentConfig, session_id: str
    ) -> AsyncIterator[RuntimeEvent]:
        await self.validate_environment()
        app = self.build_adk_app(config)
        session_service = create_adk_session_service()
        yield RuntimeEvent(
            type="adk.ready",
            payload={
                "app_name": app.name,
                "session_id": session_id,
                "session_service": str(session_service),
            },
        )

    def _normalize_agent_name(self, value: str) -> str:
        normalized = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
        return normalized or "voicelab_agent"

    def _elevenlabs_voice_id(self, voice: str) -> str:
        settings = get_settings()
        if voice == "Rachel":
            return settings.elevenlabs_voice_id_rachel
        raise RuntimeError(f"Unsupported ElevenLabs voice: {voice}")
