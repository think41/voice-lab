from app.services.tts_evaluation_pricing import (
    compute_all_model_costs,
    compute_model_cost,
    pricing_model_name,
)


def test_deepgram_voice_suffixed_models_resolve_to_aura_2() -> None:
    for voice_model in (
        "aura-2",
        "aura-2-thalia-en",
        "aura-2-asteria-en",
        "aura-2-luna-en",
        "aura-2-orion-en",
    ):
        assert pricing_model_name(provider="deepgram", model=voice_model) == "aura-2"


def test_deepgram_legacy_aura_voice_suffixes_resolve_to_aura() -> None:
    for voice_model in ("aura", "aura-luna-en", "aura-orion-en"):
        assert pricing_model_name(provider="deepgram", model=voice_model) == "aura"


def test_elevenlabs_dash_variants_alias_to_underscore_model_ids() -> None:
    assert (
        pricing_model_name(provider="elevenlabs", model="turbo-v2-5")
        == "eleven_turbo_v2_5"
    )


def test_elevenlabs_exact_model_ids_pass_through() -> None:
    assert (
        pricing_model_name(provider="elevenlabs", model="eleven_turbo_v2_5")
        == "eleven_turbo_v2_5"
    )


def test_compute_model_cost_uses_resolved_rate() -> None:
    # 1M chars on aura-2 should be $30
    assert compute_model_cost(1_000_000, provider="deepgram", model="aura-2-thalia-en") == 30.0
    # 1M chars on eleven_turbo_v2_5 should be $82.50
    assert (
        compute_model_cost(1_000_000, provider="elevenlabs", model="turbo-v2-5")
        == 82.5
    )


def test_compute_model_cost_returns_zero_for_unknown_model() -> None:
    assert compute_model_cost(1_000_000, provider="deepgram", model="unknown") == 0.0
    assert compute_model_cost(1_000_000, provider="unknown", model="whatever") == 0.0


def test_compute_all_model_costs_covers_full_model_list() -> None:
    costs = compute_all_model_costs(1_000_000)
    assert costs["deepgram"] == {"aura-2": 30.0, "aura": 15.0}
    assert costs["elevenlabs"] == {"eleven_turbo_v2_5": 82.5}


def test_compute_costs_clamp_negative_characters_to_zero() -> None:
    assert compute_model_cost(-100, provider="deepgram", model="aura-2") == 0.0
