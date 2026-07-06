from app.services.deepgram_usage import _parse_detail


def test_parse_detail_extracts_tts_usage() -> None:
    detail = {
        "response": {
            "details": {
                "usd": 0.42,
                "method": "speak.v1",
                "deployment": "api",
                "models": ["aura-asteria-en"],
            },
            "tts_details": {
                "speech_segments": [
                    {"characters": 10, "tier": "base"},
                    {"characters": 15, "tier": "base"},
                ]
            },
        }
    }

    payload = _parse_detail("tts", "req-1", detail)

    assert payload == {
        "provider": "deepgram",
        "kind": "tts",
        "request_id": "req-1",
        "usd": 0.42,
        "method": "speak.v1",
        "deployment": "api",
        "models": ["aura-asteria-en"],
        "characters": 25,
        "tier": "base",
    }
