import logging
import os
from base64 import b64encode
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import Runner
from google.genai import types

from app.core.config import get_settings
from app.schemas.agent import AgentConfig
from app.services.adk_session_service import create_adk_session_service
from app.services.voice_runtime import RuntimeEvent, VoiceRuntime

logger = logging.getLogger("uvicorn.error")


class PipecatAdkRuntime(VoiceRuntime):
    async def validate_environment(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required to run a voice test call")
        if settings.stt_provider != "deepgram":
            raise RuntimeError(f"Unsupported STT provider: {settings.stt_provider}")
        if not settings.stt_api_key:
            raise RuntimeError("STT_API_KEY is required to transcribe microphone audio")
        if settings.tts_provider != "elevenlabs":
            raise RuntimeError(f"Unsupported TTS provider: {settings.tts_provider}")
        if not settings.tts_api_key:
            raise RuntimeError("TTS_API_KEY is required to speak agent responses")
        logger.info(
            "voice runtime validated gemini_key=%s stt_provider=%s stt_key=%s "
            "tts_provider=%s tts_key=%s",
            "set",
            settings.stt_provider,
            "set",
            settings.tts_provider,
            "set",
        )

    async def synthesize_first_message(self, config: AgentConfig) -> RuntimeEvent:
        return await self.synthesize_text(config, config.first_message)

    async def synthesize_text(self, config: AgentConfig, text: str) -> RuntimeEvent:
        settings = get_settings()
        if config.tts_provider != "elevenlabs":
            raise RuntimeError(f"Unsupported TTS provider: {config.tts_provider}")
        if not settings.tts_api_key:
            raise RuntimeError("TTS_API_KEY is required to speak agent responses")

        voice_id = self._elevenlabs_voice_id(config.tts_voice)
        logger.info(
            "elevenlabs tts request voice=%s voice_id=%s text_chars=%d",
            config.tts_voice,
            voice_id,
            len(text),
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "xi-api-key": settings.tts_api_key,
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.error("elevenlabs tts failed status=%d", status_code)
                if status_code in {401, 403}:
                    raise RuntimeError(
                        "ElevenLabs rejected TTS_API_KEY. Replace it with a valid "
                        "ElevenLabs API key and restart the FastAPI server."
                    ) from exc
                detail = exc.response.text[:240]
                raise RuntimeError(
                    f"ElevenLabs TTS failed with HTTP {status_code}: {detail}"
                ) from exc
        logger.info("elevenlabs tts response bytes=%d", len(response.content))

        return RuntimeEvent(
            type="audio.output",
            payload={
                "text": text,
                "mime_type": "audio/mpeg",
                "audio_base64": b64encode(response.content).decode("ascii"),
            },
        )

    async def generate_agent_response(
        self,
        config: AgentConfig,
        session_id: str,
        user_text: str,
        user_id: str = "local-user",
    ) -> str:
        settings = get_settings()
        if settings.gemini_api_key:
            os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
            os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)

        app = self.build_adk_app(config)
        session_service = create_adk_session_service()
        existing = await session_service.get_session(
            app_name=app.name,
            user_id=user_id,
            session_id=session_id,
        )
        if existing is None:
            await session_service.create_session(
                app_name=app.name,
                user_id=user_id,
                session_id=session_id,
            )
            logger.info(
                "adk session created app=%s user_id=%s session_id=%s", app.name, user_id, session_id
            )

        runner = Runner(app=app, session_service=session_service)
        message = types.Content(role="user", parts=[types.Part(text=user_text)])
        response_parts: list[str] = []
        logger.info("adk turn start session_id=%s transcript_chars=%d", session_id, len(user_text))
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            invocation_id=f"voice-{uuid4()}",
            new_message=message,
        ):
            event_text = self._event_text(event)
            if event_text:
                response_parts.append(event_text)
            if getattr(event, "error_message", None):
                logger.error(
                    "adk event error session_id=%s error=%s", session_id, event.error_message
                )
        response_text = "".join(response_parts).strip()
        if not response_text:
            response_text = "I heard you, but I could not produce a response."
        logger.info(
            "adk turn complete session_id=%s response_chars=%d", session_id, len(response_text)
        )
        return response_text

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

    def _event_text(self, event: object) -> str:
        content = getattr(event, "content", None)
        if content is None:
            return ""
        parts = getattr(content, "parts", None) or []
        return "".join(getattr(part, "text", None) or "" for part in parts)

    def _normalize_agent_name(self, value: str) -> str:
        normalized = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
        return normalized or "voicelab_agent"

    def _elevenlabs_voice_id(self, voice: str) -> str:
        settings = get_settings()
        if voice == "Rachel":
            return settings.elevenlabs_voice_id_rachel
        raise RuntimeError(f"Unsupported ElevenLabs voice: {voice}")
