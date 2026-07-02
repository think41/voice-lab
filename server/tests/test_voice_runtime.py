import pytest

from app.schemas.agent import AgentConfig
from app.services.pipecat_adk_runtime import PipecatAdkRuntime


def test_agent_name_normalization() -> None:
    runtime = PipecatAdkRuntime()
    assert runtime._normalize_agent_name("Hotel Booking Agent") == "hotel_booking_agent"
    assert runtime._normalize_agent_name("41") == "agent_41"
    assert runtime._normalize_agent_name("---") == "voicelab_agent"


def test_build_adk_app_uses_ui_config() -> None:
    runtime = PipecatAdkRuntime()
    config = AgentConfig(
        name="Hotel Booking",
        model="gemini-2.5-flash",
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
    assert runtime._deepgram_voice_model("aura-2-selene-en") == "aura-2-selene-en"
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
