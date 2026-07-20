from pydantic import ValidationError

from app.schemas.agent import AgentConfig, llm_provider_for_model


def test_agent_config_defaults() -> None:
    config = AgentConfig(name='Support Agent')
    assert config.name == 'Support Agent'
    assert config.model == 'gemini-3.5-flash'
    assert config.temperature == 0.4


def test_agent_config_normalizes_unsupported_saved_model() -> None:
    config = AgentConfig(name='Support Agent', model='llama-3.3-70b-versatile')
    assert config.model == 'gemini-3.5-flash'


def test_agent_config_normalizes_speech_provider_defaults() -> None:
    config = AgentConfig(
        name='Support Agent',
        stt_provider='unknown',
        stt_model='bad-model',
        tts_provider='unknown',
        tts_voice='',
    )
    assert config.stt_provider == 'deepgram'
    assert config.stt_model == 'nova-3'
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


def test_llm_provider_for_model_derives_provider_from_prefix() -> None:
    assert llm_provider_for_model('gemini-3.5-flash') == 'gemini'
    assert llm_provider_for_model('openai/gpt-5.1') == 'openai'
    assert llm_provider_for_model('anthropic/claude-sonnet-5') == 'anthropic'
    assert llm_provider_for_model('xai/grok-4') == 'xai'
    assert llm_provider_for_model('groq/llama-3.3-70b-versatile') == 'groq'


def test_agent_config_accepts_openai_and_anthropic_models() -> None:
    config = AgentConfig(name='Support Agent', model='openai/gpt-5.1')
    assert config.model == 'openai/gpt-5.1'
    config = AgentConfig(name='Support Agent', model='anthropic/claude-sonnet-5')
    assert config.model == 'anthropic/claude-sonnet-5'
    config = AgentConfig(name='Support Agent', model='xai/grok-4')
    assert config.model == 'xai/grok-4'
    config = AgentConfig(name='Support Agent', model='groq/llama-3.1-8b-instant')
    assert config.model == 'groq/llama-3.1-8b-instant'


def test_agent_config_still_normalizes_unknown_models_to_default() -> None:
    config = AgentConfig(name='Support Agent', model='mistral/mistral-large')
    assert config.model == 'gemini-3.5-flash'
