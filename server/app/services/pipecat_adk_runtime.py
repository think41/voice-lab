from collections.abc import AsyncIterator

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
