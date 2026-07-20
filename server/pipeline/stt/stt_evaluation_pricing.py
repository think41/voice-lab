from __future__ import annotations

from decimal import Decimal

RATE_PER_MINUTE_USD: dict[str, dict[str, Decimal]] = {
    "deepgram": {
        "nova-3": Decimal("0.0043"),
        "nova-3-streaming": Decimal("0.0077"),
        "nova-3-multilingual": Decimal("0.0043"),
    },
    "elevenlabs": {
        "scribe-v2": Decimal("0.00367"),
        "scribe-v2-realtime": Decimal("0.0065"),
    },
    "sarvam": {
        "saarika": Decimal("0.005263"),
        "saarika-diarization": Decimal("0.007895"),
    },
}

PRODUCTION_MODEL_BY_PROVIDER = {
    "deepgram": "nova-3",
    "elevenlabs": "scribe_v2",
    "sarvam": "saarika:v2",
}

PRICING_MODEL_ALIASES = {
    "deepgram": {
        "nova-3": "nova-3",
        "nova-3-monolingual": "nova-3",
        "nova-3-streaming": "nova-3-streaming",
        "nova-3-multilingual": "nova-3-multilingual",
    },
    "elevenlabs": {
        "scribe_v1": "scribe-v2",
        "scribe_v1_experimental": "scribe-v2",
        "scribe_v2": "scribe-v2",
        "scribe-v2": "scribe-v2",
        "scribe-v2-realtime": "scribe-v2-realtime",
    },
    "sarvam": {
        "saarika:v1": "saarika",
        "saarika:v2": "saarika",
        "saarika:v2.5": "saarika",
        "saarika:flash": "saarika",
        "saarika:diarization": "saarika-diarization",
        "saarika-v2-diarization": "saarika-diarization",
        "saarika-diarization": "saarika-diarization",
        "saarika-v1": "saarika",
        "saarika-v2": "saarika",
        "saarika": "saarika",
    },
}


def compute_duration_seconds(
    audio: bytes,
    *,
    sample_rate: int,
    num_channels: int,
    bytes_per_sample: int = 2,
) -> float:
    if sample_rate <= 0 or num_channels <= 0 or bytes_per_sample <= 0:
        return 0.0
    total_samples = len(audio) / (bytes_per_sample * num_channels)
    return round(total_samples / sample_rate, 3)


def compute_model_cost(duration_sec: float, *, provider: str, model: str) -> float:
    pricing_model = pricing_model_name(provider=provider, model=model)
    rate = RATE_PER_MINUTE_USD.get(provider, {}).get(pricing_model)
    if rate is None:
        return 0.0
    duration_minutes = Decimal(str(duration_sec)) / Decimal("60")
    return _q(duration_minutes * rate)


def compute_all_model_costs(duration_sec: float) -> dict[str, dict[str, float]]:
    duration_minutes = Decimal(str(duration_sec)) / Decimal("60")
    return {
        provider: {model: _q(duration_minutes * rate) for model, rate in models.items()}
        for provider, models in RATE_PER_MINUTE_USD.items()
    }


def compute_session_model_costs(duration_sec: float) -> dict[str, dict[str, float]]:
    return compute_all_model_costs(duration_sec)


def pricing_model_name(*, provider: str, model: str) -> str:
    return PRICING_MODEL_ALIASES.get(provider, {}).get(model, model)


def _q(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001")))
