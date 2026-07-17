import logging
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.planners import BuiltInPlanner
from google.adk.runners import Runner
from google.genai import types

from app.core.config import get_settings
from app.schemas.agent import (
    LEGACY_DEEPGRAM_VOICES,
    SUPPORTED_DEEPGRAM_VOICES,
    AgentConfig,
    llm_provider_for_model,
)
from app.services.adk_session_service import create_adk_session_service, ensure_adk_session

TraceRecorder = Callable[[str, dict[str, Any]], Awaitable[None]]

logger = logging.getLogger("uvicorn.error")

# provider -> (Settings attribute, env var the ADK/LiteLLM client reads)
LLM_PROVIDER_KEYS = {
    "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
}


def require_llm_api_key(config: AgentConfig) -> None:
    provider = llm_provider_for_model(config.model)
    settings_attr, env_name = LLM_PROVIDER_KEYS[provider]
    if not getattr(get_settings(), settings_attr):
        raise RuntimeError(
            f"{env_name} is required to run model {config.model!r}"
        )


class PipecatAdkRuntime:
    async def generate_agent_response(
        self,
        config: AgentConfig,
        session_id: str,
        user_text: str,
        user_id: str = "local-user",
        record_trace: TraceRecorder | None = None,
    ) -> str:
        self.configure_provider_env(config)
        app = self.build_adk_app(config)
        session_service = create_adk_session_service()
        await ensure_adk_session(
            session_service, app_name=app.name, user_id=user_id, session_id=session_id
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
                provider = llm_provider_for_model(config.model)
                logger.error(
                    "adk quota exhausted session_id=%s provider=%s", session_id, provider
                )
                raise RuntimeError(
                    f"The {provider} API quota is exhausted for the configured key/model "
                    f"({config.model}). Use a key with available quota or switch models, "
                    "then restart the FastAPI server."
                ) from exc
            raise
        response_text = self.clean_model_text("".join(response_parts)).strip()
        if not response_text:
            response_text = "I heard you, but I could not produce a response."
        logger.info(
            "adk turn complete session_id=%s response_chars=%d", session_id, len(response_text)
        )
        return response_text

    def build_adk_app(self, config: AgentConfig) -> App:
        from pipecat_adk import AdkInterruptionPlugin

        self.configure_provider_env(config)
        agent_kwargs: dict[str, Any] = {}
        if llm_provider_for_model(config.model) == "gemini":
            # BuiltInPlanner/ThinkingConfig are Gemini-specific (google.genai types).
            agent_kwargs["planner"] = BuiltInPlanner(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
        agent = Agent(
            name=self._normalize_agent_name(config.name),
            model=config.model,
            instruction=config.instruction,
            generate_content_config=types.GenerateContentConfig(
                temperature=config.temperature,
            ),
            **agent_kwargs,
        )
        return App(name="voicelab", root_agent=agent, plugins=[AdkInterruptionPlugin()])

    def configure_provider_env(self, config: AgentConfig) -> None:
        settings = get_settings()
        provider = llm_provider_for_model(config.model)
        if provider == "gemini" and settings.gemini_api_key:
            os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
            os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)
        elif provider == "openai" and settings.openai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
        elif provider == "anthropic" and settings.anthropic_api_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)

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
        return get_settings().deepgram_api_key

    def _deepgram_voice_model(self, voice: str) -> str:
        if voice in LEGACY_DEEPGRAM_VOICES:
            return LEGACY_DEEPGRAM_VOICES[voice]
        if voice in SUPPORTED_DEEPGRAM_VOICES:
            return voice
        raise RuntimeError(f"Unsupported Deepgram voice: {voice}")
