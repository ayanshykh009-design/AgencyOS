"""LLMService: provider-agnostic facade over chat, streaming and embeddings.

Callers depend on this class (not a provider directly). The selected provider
client is injected, so the service is fully testable with a fake client. Token
usage is forwarded to an injectable recorder (by default the existing
``ProviderUsageService`` daily rollup) when one is wired up.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeVar

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.errors import AppError
from app.core.metrics import get_counter, get_histogram
from app.llm.models import (
    ChatResult,
    EmbedResult,
    LLMMessage,
    LLMUsage,
    ToolDefinition,
)
from app.llm.providers import ProviderClient
from app.services.provider_usage_service import ProviderUsageService

logger = logging.getLogger("agencyos")

T = TypeVar("T")

# HTTP statuses worth retrying: rate limits and server-side hiccups.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    """Transient provider failures only — never auth or validation errors."""
    if isinstance(exc, httpx.HTTPError):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _RETRYABLE_STATUS:
        return True
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return isinstance(status, int) and status in _RETRYABLE_STATUS


async def _async_sleep(seconds: float) -> None:
    """Indirection over ``asyncio.sleep`` so tests can fast-forward backoff."""
    import asyncio

    await asyncio.sleep(seconds)


async def _with_retry(coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Run ``coro_factory`` with exponential backoff on transient errors."""
    from app.core.config import settings

    async def _call() -> T:
        return await coro_factory()

    retrier = AsyncRetrying(
        sleep=_async_sleep,
        reraise=True,
        stop=stop_after_attempt(max(1, settings.LLM_MAX_RETRIES)),
        wait=wait_exponential(
            multiplier=1.0,
            min=max(0.1, settings.LLM_RETRY_MIN_BACKOFF),
            max=max(0.1, settings.LLM_RETRY_MAX_BACKOFF),
        ),
        retry=retry_if_exception(_is_retryable),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    return await retrier(_call)


class LLMService:
    """Business entry point for LLM calls; tracks usage and selects providers."""

    def __init__(
        self,
        client: ProviderClient | None = None,
        *,
        organization_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
        feature: str = "llm.call",
        usage_record: Callable[[LLMUsage, str], Awaitable[None]] | None = None,
    ) -> None:
        self._client = client
        self.organization_id = organization_id
        self._session = session
        self._feature = feature
        self._usage_record = usage_record

    @property
    def client(self) -> ProviderClient:
        if self._client is None:
            raise RuntimeError("LLMService has no client — configure one via for_provider()")
        return self._client

    @property
    def provider(self) -> str:
        return self.client.provider

    @property
    def model(self) -> str:
        return self.client.model

    @classmethod
    def for_provider(
        cls,
        provider: str,
        *,
        model: str | None = None,
        organization_id: uuid.UUID | None = None,
        session: AsyncSession | None = None,
        feature: str = "llm.call",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> LLMService:
        """Build a service wired to the provider named in config."""
        from app.core.config import settings
        from app.llm.providers import client_for

        resolved_model = model or settings.LLM_DEFAULT_MODEL
        key: str | None
        if provider == "openai":
            key = api_key or settings.OPENAI_API_KEY
        elif provider == "anthropic":
            key = api_key or settings.ANTHROPIC_API_KEY
        elif provider == "gemini":
            key = api_key or settings.GEMINI_API_KEY
        elif provider in ("openai-compatible", "ollama", "deepseek"):
            key = api_key
        else:
            raise ValueError(f"unsupported LLM provider: {provider!r}")

        client = client_for(
            provider,
            model=resolved_model,
            api_key=key,
            base_url=base_url,
        )
        return cls(
            client=client,
            organization_id=organization_id,
            session=session,
            feature=feature,
        )

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        await self._enforce_budget()
        result = await _with_retry(
            lambda: self.client.chat(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
        )
        if isinstance(result, ChatResult):
            await self._record(result.usage)
            return result
        raise TypeError("non-streaming chat returned an iterator")  # pragma: no cover

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatResult]:
        await self._enforce_budget()
        iterator = await _with_retry(
            lambda: self.client.chat(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
        )
        if not hasattr(iterator, "__aiter__"):
            raise TypeError("provider does not support streaming")
        final_usage: LLMUsage | None = None
        async for chunk in iterator:
            final_usage = chunk.usage
            yield chunk
        if final_usage is not None:
            await self._record(final_usage)

    async def _enforce_budget(self) -> None:
        """M11-B: block AI execution when the rolling per-org budget is exceeded.

        Evaluated against the ``provider_usage`` rollup filtered to the ``ai.``
        feature prefix (all AI-run execution) over the last 24h.

        Semantics are **fail closed**:

        * At least one positive budget must be configured. When BOTH the token
          and cost budgets are ``<= 0`` the organization has no AI budget, so
          AI execution is denied. A zero budget is **never** treated as
          "unlimited".
        * Budget-infrastructure failures also fail closed (deny) so an outage
          cannot silently grant unlimited AI.
        * A met-or-exceeded budget raises a deterministic 429.
        """
        if self._session is None or self.organization_id is None:
            return
        token_budget = settings.AI_ORG_DAILY_TOKEN_BUDGET
        cost_budget = settings.AI_ORG_DAILY_COST_BUDGET_USD

        # No budget configured at all -> AI execution is unavailable.
        if token_budget <= 0 and cost_budget <= 0:
            get_counter(
                "ai_budget_not_configured",
                description="AI run blocked: organization has no AI budget configured",
            ).add()
            raise AppError(
                code="ai.budget_not_configured",
                message="AI usage budget is not configured for this organization",
                status_code=403,
            )

        try:
            totals = await ProviderUsageService(self._session).totals_since(
                self.organization_id,
                since=datetime.now(UTC) - timedelta(hours=24),
                feature_prefix="ai.",
            )
        except Exception as exc:  # infra failure -> fail closed (deny)
            logger.warning("AI budget check failed; denying: %s", exc)
            get_counter(
                "ai_budget_check_error",
                description="AI budget check failed; execution denied (fail closed)",
            ).add()
            raise AppError(
                code="ai.budget_check_failed",
                message="AI budget could not be verified; execution denied",
                status_code=503,
            ) from None

        used_tokens = int(totals["input_tokens"]) + int(totals["output_tokens"])
        used_cost = float(totals["cost_usd"])
        if token_budget > 0 and used_tokens >= token_budget:
            get_counter(
                "ai_budget_exceeded",
                description="AI run blocked by per-org daily token budget",
            ).add()
            raise AppError(
                code="ai.budget_exceeded",
                message="AI daily token budget exceeded for this organization",
                status_code=429,
            )
        if cost_budget > 0 and used_cost >= cost_budget:
            get_counter(
                "ai_budget_exceeded",
                description="AI run blocked by per-org daily cost budget",
            ).add()
            raise AppError(
                code="ai.budget_exceeded",
                message="AI daily cost budget exceeded for this organization",
                status_code=429,
            )

    async def embeddings(self, inputs: list[str]) -> EmbedResult:
        result = await _with_retry(lambda: self.client.embeddings(inputs))
        await self._record(result.usage)
        return result

    async def _record(self, usage: LLMUsage) -> None:
        """Roll usage into attribution (provider_usage rollup by default)."""
        if self._feature.startswith("ai."):
            get_counter(
                "ai_tokens_used",
                description="Total tokens consumed by AI-run execution",
            ).add(usage.input_tokens + usage.output_tokens)
            get_histogram(
                "ai_cost",
                description="Total cost (USD) of AI-run execution",
                unit="usd",
            ).observe(usage.cost_usd)
        if self._usage_record is not None:
            await self._usage_record(usage, self._feature)
            return
        if self._session is None or self.organization_id is None:
            return

        await ProviderUsageService(self._session).record(
            organization_id=self.organization_id,
            provider=usage.provider,
            feature=self._feature,
            usage_date=date.today(),
            request_count=1,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            metadata={"model": usage.model},
        )

    # -- prompt rendering is provided by app.llm.prompts.PromptManager ------

    def render_prompt(self, name: str, version: str, variables: dict[str, Any]) -> str:
        """Render a versioned prompt from the prompts library (delegates)."""
        from app.llm.prompts import PromptManager

        return PromptManager().render(name=name, version=version, variables=variables)


def default_client() -> ProviderClient:
    """Return the configured default provider client (no usage recording).

    Convenience for ad-hoc calls where org attribution is handled elsewhere.
    """
    from app.core.config import settings
    from app.llm.providers import client_for

    model = settings.LLM_DEFAULT_MODEL
    provider = settings.LLM_PROVIDER
    key: str | None = None
    base_url: str | None = None
    if provider == "openai":
        key = settings.OPENAI_API_KEY
    elif provider == "anthropic":
        key = settings.ANTHROPIC_API_KEY
    elif provider == "gemini":
        key = settings.GEMINI_API_KEY
    elif provider in ("openai-compatible", "ollama", "deepseek"):
        base_url = settings.LLM_BASE_URL or key
    return client_for(provider, model=model, api_key=key, base_url=base_url)
