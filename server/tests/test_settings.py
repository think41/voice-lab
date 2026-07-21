from app.core.config import Settings


def test_settings_have_llm_provider_key_fields(monkeypatch) -> None:
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_api_key is None
    assert settings.anthropic_api_key is None
