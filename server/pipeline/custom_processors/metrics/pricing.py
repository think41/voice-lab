"""Rate table and cost computation for run usage summaries."""

from decimal import Decimal
from typing import Any

# LLM rates: USD per 1M input / output tokens.
LLM_RATES: dict[str, dict[str, Decimal]] = {
    "gemini-3.5-flash": {"input_per_1m": Decimal("1.50"), "output_per_1m": Decimal("9.00")},
    "gemini-3.1-flash-lite": {"input_per_1m": Decimal("0.10"), "output_per_1m": Decimal("0.40")},
    # Legacy (deprecated by Google, kept so historical runs still cost-compute).
    "gemini-2.5-flash": {"input_per_1m": Decimal("0.30"), "output_per_1m": Decimal("2.50")},
    "gemini-2.5-pro": {"input_per_1m": Decimal("1.25"), "output_per_1m": Decimal("10.00")},
    "gemini-2.0-flash": {"input_per_1m": Decimal("0.10"), "output_per_1m": Decimal("0.40")},
    "gpt-4o": {"input_per_1m": Decimal("2.50"), "output_per_1m": Decimal("10.00")},
    "gpt-4o-mini": {"input_per_1m": Decimal("0.15"), "output_per_1m": Decimal("0.60")},
    "claude-sonnet-4-5": {"input_per_1m": Decimal("3.00"), "output_per_1m": Decimal("15.00")},
    "claude-haiku-4-5": {"input_per_1m": Decimal("1.00"), "output_per_1m": Decimal("5.00")},
    "groq/llama-3.3-70b-versatile": {
        "input_per_1m": Decimal("0.59"),
        "output_per_1m": Decimal("0.79"),
    },
}

# STT rates: USD per audio-minute submitted.
STT_RATES: dict[str, Decimal] = {
    "deepgram:nova-3": Decimal("0.0043"),
    "deepgram:nova-2": Decimal("0.0043"),
    "deepgram:base": Decimal("0.0125"),
}

# TTS rates: USD per 1M characters synthesized.
TTS_RATES: dict[str, Decimal] = {
    "deepgram:aura-2": Decimal("30.00"),
    "deepgram:aura": Decimal("15.00"),
    "elevenlabs:multilingual-v2": Decimal("165.00"),
    "openai:tts-1": Decimal("15.00"),
}


def _llm_cost(payload: dict[str, Any]) -> Decimal:
    model = str(payload.get("model") or "")
    rates = LLM_RATES.get(model)
    if rates is None:
        return Decimal("0")
    prompt = Decimal(int(payload.get("prompt_tokens") or 0))
    completion = Decimal(int(payload.get("completion_tokens") or 0))
    million = Decimal("1000000")
    return (prompt / million) * rates["input_per_1m"] + (completion / million) * rates[
        "output_per_1m"
    ]


def _stt_cost(payload: dict[str, Any]) -> Decimal:
    key = f"{payload.get('provider') or 'deepgram'}:{payload.get('model') or ''}"
    rate = STT_RATES.get(key)
    if rate is None:
        return Decimal("0")
    seconds = Decimal(str(payload.get("audio_seconds") or 0))
    return (seconds / Decimal("60")) * rate


def _tts_cost(payload: dict[str, Any]) -> Decimal:
    key = f"{payload.get('provider') or 'deepgram'}:{payload.get('model') or ''}"
    rate = TTS_RATES.get(key)
    if rate is None:
        return Decimal("0")
    chars = Decimal(int(payload.get("characters") or 0))
    return (chars / Decimal("1000000")) * rate


def compute_cost(event_type: str, payload: dict[str, Any]) -> Decimal:
    """Cost of a single usage event. Unknown model or event_type returns 0."""
    if event_type == "usage.llm":
        return _llm_cost(payload)
    if event_type == "usage.stt":
        return _stt_cost(payload)
    if event_type == "usage.tts":
        return _tts_cost(payload)
    return Decimal("0")


def session_totals(events: list[Any]) -> dict[str, Any]:
    """Aggregate usage + cost + latency per component from a list of trace events.

    `events` items must expose `.event_type` and `.payload` (dict).

    Latency sources:
      - `latency.ttfb` from Pipecat's TTFBMetricsData (voice path, per turn)
      - `latency_ms` field on `usage.llm` payload (text path — timed inline)
    """
    llm_prompt = llm_completion = llm_total = 0
    local_stt_seconds = Decimal("0")
    local_tts_chars = 0
    llm_cost = local_stt_cost = local_tts_cost = Decimal("0")
    llm_latencies_ms: list[float] = []
    tts_latencies_ms: list[float] = []

    for event in events:
        if event.event_type == "usage.llm":
            payload = event.payload or {}
            llm_prompt += int(payload.get("prompt_tokens") or 0)
            llm_completion += int(payload.get("completion_tokens") or 0)
            llm_total += int(payload.get("total_tokens") or 0)
            llm_cost += _llm_cost(payload)
            inline_latency = payload.get("latency_ms")
            if inline_latency:
                llm_latencies_ms.append(float(inline_latency))
        elif event.event_type == "usage.stt":
            payload = event.payload or {}
            local_stt_seconds += Decimal(str(payload.get("audio_seconds") or 0))
            local_stt_cost += _stt_cost(payload)
        elif event.event_type == "usage.tts":
            payload = event.payload or {}
            local_tts_chars += int(payload.get("characters") or 0)
            local_tts_cost += _tts_cost(payload)
        elif event.event_type == "latency.ttfb":
            payload = event.payload or {}
            processor = str(payload.get("processor") or "").lower()
            seconds = float(payload.get("seconds") or 0)
            if seconds <= 0:
                continue
            ms = seconds * 1000.0
            if "tts" in processor:
                tts_latencies_ms.append(ms)
            elif "llm" in processor or "adk" in processor:
                llm_latencies_ms.append(ms)

    stt_seconds = local_stt_seconds
    tts_chars = local_tts_chars
    stt_cost = local_stt_cost
    tts_cost = local_tts_cost
    total_cost = llm_cost + stt_cost + tts_cost
    return {
        "llm": {
            "prompt_tokens": llm_prompt,
            "completion_tokens": llm_completion,
            "total_tokens": llm_total,
            "cost_usd": _q(llm_cost),
            "avg_latency_ms": _avg(llm_latencies_ms),
            "source": "runtime",
        },
        "stt": {
            "audio_seconds": _q(stt_seconds, "0.001"),
            "cost_usd": _q(stt_cost),
            "source": "runtime",
        },
        "tts": {
            "characters": tts_chars,
            "cost_usd": _q(tts_cost),
            "avg_latency_ms": _avg(tts_latencies_ms),
            "source": "runtime",
        },
        "total_cost_usd": _q(total_cost),
    }


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def _q(value: Decimal, quant: str = "0.000001") -> float:
    return float(value.quantize(Decimal(quant)))
