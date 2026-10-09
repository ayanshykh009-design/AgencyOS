"""M11-B: cumulative per-org token/cost budget enforcement (LLMService).

Semantics are FAIL CLOSED:
* Both budgets <= 0  -> AI execution denied (not configured = no unlimited).
* Either budget > 0  -> that dimension is enforced; the zero dimension is simply
  uncapped (not "unlimited" because the other dimension still caps usage).
* Budget-infra failure -> execution denied (fail closed, not fail open).
* Met-or-exceeded budget -> deterministic 429.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.llm.models import LLMMessage, MessageRole
from app.llm.providers import ProviderClient
from app.llm.service import LLMService


class _NoCallClient(ProviderClient):
    """Fails the test if the LLM is actually invoked (budget should block first)."""

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return "gpt-4o-mini"

    async def chat(self, messages, *, tools=None, temperature=None, max_tokens=None, stream=False):
        raise AssertionError("LLM client was called despite budget block")


def _service() -> LLMService:
    svc = LLMService(_NoCallClient())
    svc.organization_id = MagicMock()
    svc._session = MagicMock()
    return svc


async def test_budget_not_configured_when_zero() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 0),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
        )
        with pytest.raises(AppError) as exc:
            await svc._enforce_budget()
        assert exc.value.code == "ai.budget_not_configured"
        assert exc.value.status_code == 403


async def test_budget_blocks_when_tokens_exceeded() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 100),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 5, "input_tokens": 100, "output_tokens": 100, "cost_usd": 1}
        )
        with pytest.raises(AppError) as exc:
            await svc._enforce_budget()
        assert exc.value.code == "ai.budget_exceeded"
        assert exc.value.status_code == 429


async def test_budget_blocks_when_cost_exceeded() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 0),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 10.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 5, "input_tokens": 1, "output_tokens": 1, "cost_usd": 20}
        )
        with pytest.raises(AppError) as exc:
            await svc._enforce_budget()
        assert exc.value.code == "ai.budget_exceeded"


async def test_budget_allows_when_under_limit() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 100),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 10.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 5, "input_tokens": 10, "output_tokens": 10, "cost_usd": 2}
        )
        await svc._enforce_budget()  # no raise


async def test_budget_zero_token_positive_cost_allows_under_cap() -> None:
    # token budget 0 means "no token cap"; cost budget still enforced.
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 0),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 10.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 5, "input_tokens": 9999, "output_tokens": 0, "cost_usd": 2}
        )
        await svc._enforce_budget()  # token uncapped, cost under cap -> allowed


async def test_budget_exactly_at_limit_blocks() -> None:
    # ">= budget" so landing exactly on the ceiling is still blocked.
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 100),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 5, "input_tokens": 100, "output_tokens": 0, "cost_usd": 0}
        )
        with pytest.raises(AppError):
            await svc._enforce_budget()


async def test_budget_exactly_at_cost_limit_blocks() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 0),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 10.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 5, "input_tokens": 0, "output_tokens": 0, "cost_usd": 10.0}
        )
        with pytest.raises(AppError):
            await svc._enforce_budget()


async def test_chat_raises_when_budget_exceeded() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 1),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 5, "input_tokens": 999, "output_tokens": 999, "cost_usd": 0}
        )
        with pytest.raises(AppError) as exc:
            await svc.chat([LLMMessage(role=MessageRole.USER, content="hi")])
        assert exc.value.code == "ai.budget_exceeded"


async def test_budget_infra_failure_fails_closed() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 100),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(side_effect=RuntimeError("db down"))
        # Must raise (fail closed) — a budget-infra failure must NOT proceed.
        with pytest.raises(AppError) as exc:
            await svc._enforce_budget()
        assert exc.value.code == "ai.budget_check_failed"
        assert exc.value.status_code == 503


async def test_budget_totals_count_all_org_features_no_feature_filter() -> None:
    """B-6 regression: the budget ceiling is per-org and must sum ALL
    provider_usage rows. Reintroducing ``feature_prefix="ai."`` lets usage
    recorded under any other feature key (e.g. "research",
    "intelligence.narrative") escape the ceiling."""
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 100),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 1, "input_tokens": 1, "output_tokens": 0, "cost_usd": 0}
        )
        await svc._enforce_budget()
        assert pus.return_value.totals_since.await_count == 1
        kwargs = pus.return_value.totals_since.await_args.kwargs
        assert kwargs.get("feature_prefix") in (None, "") or "feature_prefix" not in kwargs


async def test_budget_blocks_when_non_namespaced_feature_spend_exceeds_ceiling() -> None:
    """B-6 behavioral: spend recorded under a non-`ai.`-prefixed feature key
    (as returned by an unfiltered totals_since) still blocks execution at the
    per-org ceiling."""
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 50),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        # Totals as ProviderUsageRepository returns them with feature_prefix
        # unset: they include rows tagged "research" / "intelligence.narrative".
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 3, "input_tokens": 40, "output_tokens": 30, "cost_usd": 0.04}
        )
        with pytest.raises(AppError) as exc:
            await svc._enforce_budget()
        assert exc.value.code == "ai.budget_exceeded"
        assert exc.value.status_code == 429
