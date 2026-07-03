from pydantic import ValidationError

from app.schemas.agent import AgentConfig


def test_agent_config_defaults() -> None:
    config = AgentConfig(name='Support Agent')
    assert config.name == 'Support Agent'
    assert config.model == 'gemini-2.5-flash'
    assert config.temperature == 0.4


def test_agent_config_normalizes_unsupported_saved_model() -> None:
    config = AgentConfig(name='Support Agent', model='llama-3.3-70b-versatile')
    assert config.model == 'gemini-2.5-flash'


def test_agent_config_normalizes_speech_provider_defaults() -> None:
    config = AgentConfig(
        name='Support Agent',
        stt_provider='unknown',
        stt_model='bad-model',
        tts_provider='unknown',
        tts_voice='',
    )
    assert config.stt_provider == 'deepgram'
    assert config.stt_model == 'nova-2'
    assert config.tts_provider == 'deepgram'
    assert config.tts_voice == 'aura-asteria-en'


def test_agent_config_supports_elevenlabs_provider_defaults() -> None:
    config = AgentConfig(
        name='Support Agent',
        stt_provider='elevenlabs',
        stt_model='invalid',
        tts_provider='elevenlabs',
        tts_voice='',
    )
    assert config.stt_provider == 'elevenlabs'
    assert config.stt_model == 'scribe_v2_realtime'
    assert config.tts_provider == 'elevenlabs'
    assert config.tts_voice == 'JBFqnCBsd6RMkjVDRZzb'


def test_agent_config_temperature_bounds() -> None:
    try:
        AgentConfig(name='Bad Agent', temperature=3)
    except ValidationError as exc:
        assert 'less than or equal to 2' in str(exc)
    else:
        raise AssertionError('Expected validation error')
