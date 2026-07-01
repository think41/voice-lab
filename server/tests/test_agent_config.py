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


def test_agent_config_temperature_bounds() -> None:
    try:
        AgentConfig(name='Bad Agent', temperature=3)
    except ValidationError as exc:
        assert 'less than or equal to 2' in str(exc)
    else:
        raise AssertionError('Expected validation error')
