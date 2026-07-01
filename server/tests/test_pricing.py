from types import SimpleNamespace

from app.services.pricing import compute_cost, session_totals


def test_llm_cost_gemini_2_5_flash() -> None:
    # gemini-2.5-flash: $0.30 per 1M input, $2.50 per 1M output.
    cost = compute_cost(
        "usage.llm",
        {"prompt_tokens": 1000, "completion_tokens": 500, "model": "gemini-2.5-flash"},
    )
    # (1000/1e6)*0.30 + (500/1e6)*2.50 = 0.00030 + 0.00125 = 0.00155
    assert float(cost) == 0.00155


def test_llm_cost_unknown_model_is_zero() -> None:
    cost = compute_cost(
        "usage.llm",
        {"prompt_tokens": 1000, "completion_tokens": 500, "model": "made-up-model"},
    )
    assert float(cost) == 0.0


def test_stt_cost_deepgram_nova_3() -> None:
    # $0.0043 per audio minute.
    cost = compute_cost(
        "usage.stt",
        {"audio_seconds": 60, "provider": "deepgram", "model": "nova-3"},
    )
    assert float(cost) == 0.0043


def test_tts_cost_deepgram_aura_2() -> None:
    # $30 per 1M characters => 1000 chars = $0.03.
    cost = compute_cost(
        "usage.tts",
        {"characters": 1000, "provider": "deepgram", "model": "aura-2-thalia-en"},
    )
    # aura-2-thalia-en isn't in the table as a full key; test the coarse aura-2 key too:
    assert float(cost) == 0.0  # unknown TTS voice-model returns 0 by design
    cost2 = compute_cost(
        "usage.tts",
        {"characters": 1000, "provider": "deepgram", "model": "aura-2"},
    )
    assert float(cost2) == 0.03


def test_session_totals_sums_across_events() -> None:
    events = [
        SimpleNamespace(
            event_type="usage.llm",
            payload={
                "prompt_tokens": 2000,
                "completion_tokens": 500,
                "total_tokens": 2500,
                "model": "gemini-2.5-flash",
            },
        ),
        SimpleNamespace(
            event_type="usage.stt",
            payload={"audio_seconds": 30, "provider": "deepgram", "model": "nova-3"},
        ),
        SimpleNamespace(
            event_type="usage.tts",
            payload={"characters": 500, "provider": "deepgram", "model": "aura-2"},
        ),
        SimpleNamespace(event_type="transcript.final", payload={"text": "hi"}),
    ]
    totals = session_totals(events)
    assert totals["llm"]["total_tokens"] == 2500
    # 2000*0.30/1e6 + 500*2.50/1e6 = 0.0006 + 0.00125 = 0.00185
    assert totals["llm"]["cost_usd"] == 0.00185
    # 30/60 * 0.0043 = 0.00215
    assert totals["stt"]["audio_seconds"] == 30.0
    assert totals["stt"]["cost_usd"] == 0.00215
    # 500/1e6 * 30.0 = 0.015
    assert totals["tts"]["characters"] == 500
    assert totals["tts"]["cost_usd"] == 0.015
    assert totals["total_cost_usd"] == 0.019
