from types import SimpleNamespace

from app.api.routes.runs import _provider_summary


def test_provider_summary_marks_elevenlabs_tts_websocket_as_unavailable() -> None:
    events = [
        SimpleNamespace(
            event_type="session.started",
            payload={
                "mode": "pipecat_streaming",
                "stt_provider": "deepgram",
                "stt_model": "nova-2",
                "tts_provider": "elevenlabs",
                "tts_voice": "JBFqnCBsd6RMkjVDRZzb",
            },
        ),
        SimpleNamespace(
            event_type="stt.provider_request",
            payload={
                "provider": "deepgram",
                "provider_request_id": "stt-123",
                "transport": "websocket",
                "model": "nova-2",
                "run_tag": "run-123",
            },
        ),
        SimpleNamespace(
            event_type="usage.tts",
            payload={
                "provider": "elevenlabs",
                "model": "eleven_turbo_v2_5",
                "characters": 21,
            },
        ),
    ]

    summary = _provider_summary(events)

    assert summary.stt.provider == "deepgram"
    assert summary.stt.provider_request_id == "stt-123"
    assert summary.stt.provider_lookup_available is True
    assert summary.tts.provider == "elevenlabs"
    assert summary.tts.model == "eleven_turbo_v2_5"
    assert summary.tts.transport == "websocket"
    assert summary.tts.provider_request_id is None
    assert summary.tts.provider_lookup_available is False
    assert summary.tts.unavailable_reason == "ElevenLabs TTS over websocket does not expose a provider request id"


def test_provider_summary_includes_deepgram_provider_usage_details() -> None:
    events = [
        SimpleNamespace(
            event_type="session.started",
            payload={
                "mode": "pipecat_streaming",
                "stt_provider": "deepgram",
                "stt_model": "nova-2",
                "tts_provider": "deepgram",
                "tts_voice": "aura-asteria-en",
            },
        ),
        SimpleNamespace(
            event_type="stt.provider_request",
            payload={
                "provider": "deepgram",
                "provider_request_id": "stt-123",
                "transport": "websocket",
                "model": "nova-2",
                "run_tag": "run-123",
            },
        ),
        SimpleNamespace(
            event_type="provider.usage",
            payload={
                "provider": "deepgram",
                "kind": "stt",
                "request_id": "stt-123",
                "usd": 0.007,
                "method": "streaming",
                "tier": "nova",
                "models": ["model-1"],
                "features": ["endpointing", "punctuate"],
            },
        ),
    ]

    summary = _provider_summary(events)

    assert summary.stt.provider_cost_usd == 0.007
    assert summary.stt.method == "streaming"
    assert summary.stt.tier == "nova"
    assert summary.stt.provider_models == ["model-1"]
    assert summary.stt.features == ["endpointing", "punctuate"]
