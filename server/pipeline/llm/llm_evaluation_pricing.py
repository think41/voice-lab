from __future__ import annotations

from decimal import Decimal

from pipeline.custom_processors.metrics.pricing import LLM_RATES

# Reuses LLM_RATES (server/pipeline/custom_processors/metrics/pricing.py) as the
# single source of truth for rates, grouped by provider for the cross-model
# comparison grid. Add a provider mapping here whenever a model is added to
# LLM_RATES; `llm_provider_for_model` isn't used because some legacy LLM_RATES
# keys (gpt-4o, claude-sonnet-4-5) predate the "provider/model" LiteLLM naming
# convention and would otherwise be misclassified as gemini (the bare-ID default).
_PROVIDER_BY_MODEL: dict[str, str] = {
    "gemini-3.5-flash": "gemini",
    "gemini-3.1-flash-lite": "gemini",
    "gemini-2.5-flash": "gemini",
    "gemini-2.5-pro": "gemini",
    "gemini-2.0-flash": "gemini",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "claude-sonnet-4-5": "anthropic",
    "claude-haiku-4-5": "anthropic",
    "groq/llama-3.3-70b-versatile": "groq",
}


def _grouped_rates() -> dict[str, dict[str, dict[str, Decimal]]]:
    grouped: dict[str, dict[str, dict[str, Decimal]]] = {}
    for model, rates in LLM_RATES.items():
        provider = _PROVIDER_BY_MODEL.get(model, "groq" if "/" in model else "gemini")
        grouped.setdefault(provider, {})[model] = {
            "input": rates["input_per_1m"],
            "output": rates["output_per_1m"],
        }
    return grouped


RATE_PER_MILLION_TOKENS_USD: dict[str, dict[str, dict[str, Decimal]]] = _grouped_rates()


def compute_model_cost(
    prompt_tokens: int, completion_tokens: int, *, provider: str, model: str
) -> float:
    rates = RATE_PER_MILLION_TOKENS_USD.get(provider, {}).get(model)
    if rates is None:
        return 0.0
    million = Decimal("1000000")
    cost = (Decimal(str(max(prompt_tokens, 0))) / million) * rates["input"] + (
        Decimal(str(max(completion_tokens, 0))) / million
    ) * rates["output"]
    return _q(cost)


def compute_all_model_costs(
    prompt_tokens: int, completion_tokens: int
) -> dict[str, dict[str, float]]:
    """Re-price this session's actual token counts against every known model's rate.

    This is necessarily an estimate for every model except the one that
    actually ran: tokenizers differ across providers, so the same
    conversation would not produce identical prompt/completion token counts
    on a different model. Mirrors the same caveat already called out for the
    STT/TTS cross-provider comparisons.
    """
    million = Decimal("1000000")
    prompt = Decimal(str(max(prompt_tokens, 0))) / million
    completion = Decimal(str(max(completion_tokens, 0))) / million
    return {
        provider: {
            model: _q(prompt * rates["input"] + completion * rates["output"])
            for model, rates in models.items()
        }
        for provider, models in RATE_PER_MILLION_TOKENS_USD.items()
    }


def _q(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001")))
