import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.planners import BuiltInPlanner
from google.adk.runners import Runner
from google.genai import types

from app.core.config import get_settings
from app.schemas.agent import AgentConfig
from app.services.adk_session_service import create_adk_session_service, ensure_adk_session

TraceRecorder = Callable[[str, dict[str, Any]], Awaitable[None]]

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


class PipecatAdkRuntime:
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

    async def generate_agent_response(
        self,
        config: AgentConfig,
        session_id: str,
        user_text: str,
        user_id: str = "local-user",
        record_trace: TraceRecorder | None = None,
    ) -> str:
        self.configure_google_api_key()
        app = self.build_adk_app(config)
        session_service = create_adk_session_service()
        await ensure_adk_session(
            session_service, app_name=app.name, user_id=user_id, session_id=session_id
        )
        runner = Runner(app=app, session_service=session_service)
        message = types.Content(role="user", parts=[types.Part(text=user_text)])
        response_parts: list[str] = []
        final_usage: Any | None = None
        logger.info("adk turn start session_id=%s transcript_chars=%d", session_id, len(user_text))
        turn_started = time.monotonic()
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
                # Gemini repeats cumulative usage on every event; the last non-partial wins.
                usage = getattr(event, "usage_metadata", None)
                if usage and not getattr(event, "partial", False):
                    final_usage = usage
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
        response_text = self.clean_model_text("".join(response_parts)).strip()
        if not response_text:
            response_text = "I heard you, but I could not produce a response."
        if record_trace is not None and final_usage is not None:
            latency_ms = round((time.monotonic() - turn_started) * 1000.0, 1)
            await record_trace(
                "usage.llm",
                {
                    "prompt_tokens": final_usage.prompt_token_count or 0,
                    "completion_tokens": final_usage.candidates_token_count or 0,
                    "total_tokens": final_usage.total_token_count or 0,
                    "cache_read_input_tokens": final_usage.cached_content_token_count or 0,
                    "reasoning_tokens": getattr(final_usage, "thoughts_token_count", None) or 0,
                    "model": config.model,
                    "processor": "adk-text",
                    "latency_ms": latency_ms,
                },
            )
        logger.info(
            "adk turn complete session_id=%s response_chars=%d", session_id, len(response_text)
        )
        return response_text

    def build_adk_app(self, config: AgentConfig) -> App:
        from pipecat_adk import AdkInterruptionPlugin

        self.configure_google_api_key()
        agent = Agent(
            name=self._normalize_agent_name(config.name),
            model=config.model,
            instruction=config.instruction,
            planner=BuiltInPlanner(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return App(name="voicelab", root_agent=agent, plugins=[AdkInterruptionPlugin()])

    def configure_google_api_key(self) -> None:
        settings = get_settings()
        if settings.gemini_api_key:
            os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
            os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)

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

    def clean_model_text(self, text: str) -> str:
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
        return text.strip()

    def _normalize_for_speech(self, text: str) -> str:
        text = self.clean_model_text(text)
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
