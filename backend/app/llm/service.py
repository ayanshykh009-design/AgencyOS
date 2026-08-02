"""LLMService: provider-agnostic facade over chat, streaming and embeddings.

Callers depend on this class (not a provider directly). The selected provider
client is injected, so the service is fully testable with a fake client. Token
usage is forwarded to an injectable recorder (by default the existing
``ProviderUsageService`` daily rollup) when one is wired up.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.models import (
    ChatResult,
    EmbedResult,
    LLMMessage,
    LLMUsage,
    ToolDefinition,
)
from app.llm.providers import ProviderClient


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
        result = await self.client.chat(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
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
        iterator = await self.client.chat(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        if not hasattr(iterator, "__aiter__"):
            raise TypeError("provider does not support streaming")
        final_usage: LLMUsage | None = None
        async for chunk in iterator:
            final_usage = chunk.usage
            yield chunk
        if final_usage is not None:
            await self._record(final_usage)

    async def embeddings(self, inputs: list[str]) -> EmbedResult:
        result = await self.client.embeddings(inputs)
        await self._record(result.usage)
        return result

    async def _record(self, usage: LLMUsage) -> None:
        """Roll usage into attribution (provider_usage rollup by default)."""
        if self._usage_record is not None:
            await self._usage_record(usage, self._feature)
            return
        if self._session is None or self.organization_id is None:
            return
        from app.services.provider_usage_service import ProviderUsageService

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
