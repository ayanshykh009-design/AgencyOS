"""Cost estimation for LLM calls.

Pricing is expressed as ``input_usd_per_1k_tokens`` / ``output_usd_per_1k_tokens``.
Values are approximate list prices used for budgeting/usage rollups, not
billing. Unknown provider/model pairs fall back to zero so callers can still
record token counts and fill prices later without code changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.llm.models import ProviderType


@dataclass(frozen=True)
class ModelPricing:
    """Per-1k-token cost for a model."""

    input_usd_per_1k: float
    output_usd_per_1k: float


# Pricing tables keyed by provider -> model -> pricing. Kept as plain data so
# the registry can be extended (and prices updated) in one place.
_PRICES: dict[str, dict[str, ModelPricing]] = {
    ProviderType.OPENAI: {
        "gpt-4o-mini": ModelPricing(0.000150, 0.000600),
        "gpt-4o": ModelPricing(0.002500, 0.001000),
        "gpt-4.1-mini": ModelPricing(0.000200, 0.000800),
        "gpt-4.1": ModelPricing(0.002000, 0.000800),
        "o1-mini": ModelPricing(0.001100, 0.004400),
    },
    ProviderType.ANTHROPIC: {
        "claude-3-5-sonnet-20241022": ModelPricing(0.000300, 0.001500),
        "claude-3-7-sonnet-20250219": ModelPricing(0.000300, 0.001500),
        "claude-3-haiku-20240307": ModelPricing(0.000025, 0.000125),
    },
    ProviderType.GEMINI: {
        "gemini-1.5-flash": ModelPricing(0.000035, 0.000105),
        "gemini-2.0-flash": ModelPricing(0.000035, 0.000105),
        "gemini-1.5-pro": ModelPricing(0.000175, 0.000700),
        "gemini-2.5-pro": ModelPricing(0.000175, 0.000700),
    },
    ProviderType.DEEPSEEK: {
        "deepseek-chat": ModelPricing(0.000001, 0.000002),
        "deepseek-reasoner": ModelPricing(0.000140, 0.000280),
    },
}


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Return the estimated USD cost for a completion, or 0.0 if unknown."""
    table = _PRICES.get(provider)
    if table is None:
        return 0.0
    pricing = table.get(model)
    if pricing is None:
        # Fall back to a best guess using the first known model for the provider.
        pricing = next(iter(table.values()), None)
        if pricing is None:
            return 0.0
    return (
        pricing.input_usd_per_1k * input_tokens / 1000.0
        + pricing.output_usd_per_1k * output_tokens / 1000.0
    )
