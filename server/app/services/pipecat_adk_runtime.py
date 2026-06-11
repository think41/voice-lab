import logging
import os
import re
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


class PipecatAdkRuntime(VoiceRuntime):
    async def validate_environment(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required to run a voice test call")
        if settings.stt_provider != "deepgram":
            raise RuntimeError(f"Unsupported STT provider: {settings.stt_provider}")
        if not settings.stt_api_key:
            raise RuntimeError("STT_API_KEY is required to transcribe microphone audio")
        if settings.tts_provider != "deepgram":
            raise RuntimeError(f"Unsupported TTS provider: {settings.tts_provider}")
        if not self._deepgram_tts_api_key():
            raise RuntimeError("STT_API_KEY or TTS_API_KEY is required to speak agent responses")
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
        api_key = self._deepgram_tts_api_key()
        if not api_key:
            raise RuntimeError("STT_API_KEY or TTS_API_KEY is required to speak agent responses")

        voice_model = self._deepgram_voice_model(config.tts_voice)
        speech_text = self._normalize_for_speech(text)
        logger.info(
            "deepgram tts request voice_model=%s text_chars=%d speech_chars=%d",
            voice_model,
            len(text),
            len(speech_text),
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.deepgram.com/v1/speak",
                params={"model": voice_model},
                headers={
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "Authorization": f"Token {api_key}",
                },
                json={"text": speech_text},
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.error("deepgram tts failed status=%d", status_code)
                if status_code in {401, 403}:
                    raise RuntimeError(
                        "Deepgram rejected the TTS key. Check STT_API_KEY/TTS_API_KEY "
                        "and restart the FastAPI server."
                    ) from exc
                detail = exc.response.text[:240]
                raise RuntimeError(
                    f"Deepgram TTS failed with HTTP {status_code}: {detail}"
                ) from exc
        logger.info("deepgram tts response bytes=%d", len(response.content))

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
        try:
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
        except Exception as exc:
            message_text = str(exc)
            if "RESOURCE_EXHAUSTED" in message_text or "429" in message_text:
                logger.error("adk quota exhausted session_id=%s", session_id)
                raise RuntimeError(
                    "Gemini quota is exhausted for the configured API key/model. "
                    "Use a key with available quota or switch to a model/project with quota, "
                    "then restart the FastAPI server."
                ) from exc
            raise
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
        if not normalized:
            return "voicelab_agent"
        if normalized[0].isdigit():
            return f"agent_{normalized}"
        return normalized

    def _normalize_for_speech(self, text: str) -> str:
        return re.sub(r"\bthink\s*41\b", "Think forty one", text, flags=re.IGNORECASE)

    def _deepgram_tts_api_key(self) -> str | None:
        settings = get_settings()
        return settings.stt_api_key or settings.tts_api_key

    def _deepgram_voice_model(self, voice: str) -> str:
        if voice in LEGACY_DEEPGRAM_VOICES:
            return LEGACY_DEEPGRAM_VOICES[voice]
        if voice in SUPPORTED_DEEPGRAM_VOICES:
            return voice
        raise RuntimeError(f"Unsupported Deepgram voice: {voice}")
