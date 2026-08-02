"""Provider client interface and factory.

A provider client is any class implementing :class:`ProviderClient`. New
providers are added in :func:`client_for`; selecting them is a config flip —
no code outside this module references a provider SDK directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from app.llm.models import ChatResult, EmbedResult, LLMMessage, ToolDefinition


class ProviderClient(Protocol):
    """Minimal interface every LLM provider client must satisfy."""

    @property
    def provider(self) -> str:
        """Canonical provider identifier (e.g. ``openai``)."""
        ...

    @property
    def model(self) -> str:
        """Resolved model name used for this client."""
        ...

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[ChatResult]:
        """Create a chat completion. Returns a full result, or an async iterator
        of deltas when ``stream`` is true."""
        ...

    async def embeddings(self, inputs: list[str]) -> EmbedResult:
        """Create embeddings for a batch of inputs."""
        ...


def _build_http_options() -> dict[str, Any]:
    """Common httpx options for provider calls."""
    return {"timeout": 60.0, "http2": True}


def client_for(
    provider: str,
    *,
    model: str,
    api_key: str | None,
    base_url: str | None = None,
    http: httpx.AsyncClient | None = None,
) -> ProviderClient:
    """Construct the client for ``provider``. Raises if dependencies are missing
    or configuration is incomplete."""
    if provider == "openai":
        from app.llm.providers.openai import OpenAIClient

        return OpenAIClient(model=model, api_key=api_key, base_url=base_url, http=http)
    if provider == "anthropic":
        from app.llm.providers.anthropic import AnthropicClient

        return AnthropicClient(model=model, api_key=api_key, http=http)
    if provider == "gemini":
        from app.llm.providers.gemini import GeminiClient

        return GeminiClient(model=model, api_key=api_key, http=http)
    if provider in ("openai-compatible", "ollama", "deepseek"):
        kind = "openai-compatible" if provider == "openai-compatible" else provider
        from app.llm.providers.openai_compatible import OpenAICompatibleClient

        return OpenAICompatibleClient(
            kind=kind, model=model, api_key=api_key, base_url=base_url, http=http
        )
    raise ValueError(f"unsupported LLM provider: {provider!r}")
