from app.services.stt_evaluation_pricing import (
    compute_all_model_costs,
    compute_duration_seconds,
    compute_model_cost,
)


def test_compute_duration_seconds_for_mono_pcm16() -> None:
    audio = b"\x00\x01" * 16000
    assert compute_duration_seconds(audio, sample_rate=16000, num_channels=1) == 1.0


def test_compute_duration_seconds_for_stereo_pcm16() -> None:
    audio = b"\x00\x01" * 32000
    assert compute_duration_seconds(audio, sample_rate=16000, num_channels=2) == 1.0


def test_compute_all_model_costs_reuses_same_duration() -> None:
    costs = compute_all_model_costs(60.0)

    assert costs["deepgram"]["nova-3"] == 0.0043
    assert costs["deepgram"]["nova-3-streaming"] == 0.0077
    assert costs["elevenlabs"]["scribe-v2"] == 0.00367
    assert costs["sarvam"]["saarika"] == 0.005263
    assert costs["sarvam"]["saarika-diarization"] == 0.007895


def test_compute_model_cost_returns_zero_for_unknown_model() -> None:
    assert compute_model_cost(60.0, provider="deepgram", model="unknown") == 0.0
