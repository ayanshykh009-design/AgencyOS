"""M11-B: cumulative per-org token/cost budget enforcement (LLMService)."""

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


async def test_budget_disabled_when_zero() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 0),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch(
            "app.llm.service.ProviderUsageService"
        ) as pus,
    ):
        pus.return_value.totals_since = AsyncMock(
            return_value={"requests": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0}
        )
        # Must not raise.
        await svc._enforce_budget()


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


async def test_budget_infra_failure_fails_open() -> None:
    svc = _service()
    with (
        patch.object(settings, "AI_ORG_DAILY_TOKEN_BUDGET", 100),
        patch.object(settings, "AI_ORG_DAILY_COST_BUDGET_USD", 0.0),
        patch("app.llm.service.ProviderUsageService") as pus,
    ):
        pus.return_value.totals_since = AsyncMock(side_effect=RuntimeError("db down"))
        # Must not raise — infra failure fails open (availability over strictness).
        await svc._enforce_budget()
