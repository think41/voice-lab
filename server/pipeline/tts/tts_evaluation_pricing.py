from __future__ import annotations

from decimal import Decimal

# USD per 1,000,000 characters sent to the TTS provider.
#
# Rates are pay-as-you-go list prices. Enterprise / committed-spend rates
# can be materially lower. Sources:
#   - Deepgram TTS pricing:  https://deepgram.com/pricing
#   - ElevenLabs pricing:    https://elevenlabs.io/pricing
#
# TTS providers price per *model*, not per *voice*. All Aura-2 voices
# (thalia, asteria, luna, orion, ...) share the aura-2 rate. All ElevenLabs
# voices used with eleven_multilingual_v2 share the same rate; the same
# voice on eleven_flash_v2_5 uses the flash rate instead.
# Sarvam bills Bulbul v2/v3 in INR per 10K characters; these are converted
# to USD using the RBI/FBIL USD reference rate from July 15, 2026
# (1 USD = INR 96.2219) so the dashboard can compare providers on the
# same currency axis.
#
# ElevenLabs bills in "credits per character" (Flash/Turbo = 0.5×,
# Multilingual v2 / v1 / Monolingual v1 = 1×, v3 alpha = 1× for now).
# The dollar-per-M-char figures below convert those credit ratios against
# the $165/M anchor used in the legacy pricing.py module.
RATE_PER_MILLION_CHARS_USD: dict[str, dict[str, Decimal]] = {
    "deepgram": {
        "aura-2": Decimal("30.00"),
        "aura": Decimal("15.00"),
    },
    "elevenlabs": {
        # UI has no ElevenLabs model dropdown; the app drives eleven_turbo_v2_5
        # as the default (see server/app/schemas/agent.py). Add more entries here
        # only when the UI actually exposes them.
        "eleven_turbo_v2_5": Decimal("82.50"),
    },
    "sarvam": {
        "bulbul:v2": Decimal("15.588967"),
        "bulbul:v3": Decimal("31.177934"),
    },
}

# Deepgram Aura model IDs are voice-suffixed at runtime (e.g. `aura-2-thalia-en`,
# `aura-2-asteria-en`). We resolve any string starting with a known prefix to the
# parent model rate, so new voices don't need explicit entries.
DEEPGRAM_MODEL_PREFIXES: tuple[str, ...] = ("aura-2", "aura")

# ElevenLabs model IDs are stable exact strings; users occasionally pass the
# dash-hyphenated variant. Map those to the underscore form used above.
ELEVENLABS_MODEL_ALIASES: dict[str, str] = {
    "v3": "eleven_v3",
    "eleven-v3": "eleven_v3",
    "multilingual-v2": "eleven_multilingual_v2",
    "eleven-multilingual-v2": "eleven_multilingual_v2",
    "multilingual-v1": "eleven_multilingual_v1",
    "monolingual-v1": "eleven_monolingual_v1",
    "flash-v2-5": "eleven_flash_v2_5",
    "flash-v2": "eleven_flash_v2",
    "turbo-v2-5": "eleven_turbo_v2_5",
    "turbo-v2": "eleven_turbo_v2",
}

SARVAM_MODEL_ALIASES: dict[str, str] = {
    "bulbul": "bulbul:v3",
    "bulbul-v2": "bulbul:v2",
    "bulbul-v3": "bulbul:v3",
    "bulbul_v2": "bulbul:v2",
    "bulbul_v3": "bulbul:v3",
}


def pricing_model_name(*, provider: str, model: str) -> str:
    if provider == "deepgram":
        for prefix in DEEPGRAM_MODEL_PREFIXES:
            if model == prefix or model.startswith(f"{prefix}-") or model.startswith(f"{prefix}_"):
                return prefix
        return model
    if provider == "elevenlabs":
        if model in RATE_PER_MILLION_CHARS_USD["elevenlabs"]:
            return model
        return ELEVENLABS_MODEL_ALIASES.get(model, model)
    if provider == "sarvam":
        if model in RATE_PER_MILLION_CHARS_USD["sarvam"]:
            return model
        return SARVAM_MODEL_ALIASES.get(model, model)
    return model


def compute_model_cost(sent_characters: int, *, provider: str, model: str) -> float:
    pricing_model = pricing_model_name(provider=provider, model=model)
    rate = RATE_PER_MILLION_CHARS_USD.get(provider, {}).get(pricing_model)
    if rate is None:
        return 0.0
    chars = Decimal(str(max(sent_characters, 0))) / Decimal("1000000")
    return _q(chars * rate)


def compute_all_model_costs(sent_characters: int) -> dict[str, dict[str, float]]:
    chars = Decimal(str(max(sent_characters, 0))) / Decimal("1000000")
    return {
        provider: {model: _q(chars * rate) for model, rate in models.items()}
        for provider, models in RATE_PER_MILLION_CHARS_USD.items()
    }


def _q(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001")))
