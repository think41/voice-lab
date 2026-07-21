import pytest

from app.schemas.agent import AgentConfig
from app.services.pipecat_adk_runtime import PipecatAdkRuntime, require_llm_api_key


def test_agent_name_normalization() -> None:
    runtime = PipecatAdkRuntime()
    assert runtime._normalize_agent_name("Hotel Booking Agent") == "hotel_booking_agent"
    assert runtime._normalize_agent_name("41") == "agent_41"
    assert runtime._normalize_agent_name("---") == "voicelab_agent"


def test_build_adk_app_uses_ui_config() -> None:
    runtime = PipecatAdkRuntime()
    config = AgentConfig(
        name="Hotel Booking",
        model="gemini-3.5-flash",
        instruction="Book hotel rooms politely.",
    )
    app = runtime.build_adk_app(config)
    assert app.name == "voicelab"
    assert app.root_agent.name == "hotel_booking"


def test_deepgram_voice_mapping_supports_current_and_legacy_saved_configs() -> None:
    runtime = PipecatAdkRuntime()
    assert runtime._deepgram_voice_model("aura-asteria-en") == "aura-asteria-en"
    assert runtime._deepgram_voice_model("aura-luna-en") == "aura-luna-en"
    assert runtime._deepgram_voice_model("aura-2-orion-en") == "aura-2-orion-en"
    assert runtime._deepgram_voice_model("Rachel") == "aura-asteria-en"


def test_deepgram_voice_mapping_rejects_unsupported_voice() -> None:
    runtime = PipecatAdkRuntime()
    with pytest.raises(RuntimeError, match="Unsupported Deepgram voice"):
        runtime._deepgram_voice_model("unknown-voice")


def test_speech_normalization_pronounces_think41_brand() -> None:
    runtime = PipecatAdkRuntime()
    assert runtime._normalize_for_speech("think41") == "Think forty one"
    assert runtime._normalize_for_speech("Think41") == "Think forty one"
    assert runtime._normalize_for_speech("Think 41") == "Think forty one"
    assert (
        runtime._normalize_for_speech("Welcome to think41. This is think 41 support.")
        == "Welcome to Think forty one. This is Think forty one support."
    )


def test_build_adk_app_attaches_planner_only_for_gemini() -> None:
    runtime = PipecatAdkRuntime()
    gemini_app = runtime.build_adk_app(AgentConfig(name="G", model="gemini-3.5-flash"))
    assert gemini_app.root_agent.planner is not None
    assert gemini_app.root_agent.model == "gemini-3.5-flash"

    claude_app = runtime.build_adk_app(
        AgentConfig(name="C", model="anthropic/claude-sonnet-5")
    )
    assert claude_app.root_agent.planner is None
    assert claude_app.root_agent.model.model == "anthropic/claude-sonnet-5"


def test_build_adk_app_wraps_non_gemini_models_in_litellm() -> None:
    from google.adk.models.lite_llm import LiteLlm

    runtime = PipecatAdkRuntime()
    for model_id in (
        "anthropic/claude-sonnet-5",
        "openai/gpt-5.1",
        "groq/llama-3.1-8b-instant",
    ):
        app = runtime.build_adk_app(AgentConfig(name="X", model=model_id))
        assert isinstance(app.root_agent.model, LiteLlm)
        assert app.root_agent.model.model == model_id


def test_require_llm_api_key_raises_when_provider_key_missing(monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        require_llm_api_key(AgentConfig(name="O", model="openai/gpt-5.1"))


def test_require_llm_api_key_passes_when_key_present(monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    require_llm_api_key(AgentConfig(name="A", model="anthropic/claude-sonnet-5"))


def test_build_adk_app_applies_temperature() -> None:
    runtime = PipecatAdkRuntime()
    app = runtime.build_adk_app(
        AgentConfig(name="T", model="gemini-3.5-flash", temperature=0.9)
    )
    assert app.root_agent.generate_content_config.temperature == 0.9
