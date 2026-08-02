"""Gemini provider client (Google Generative AI).

Uses the ``google-generativeai`` SDK, which is an optional dependency. Importing
it here means a deployment that never selects the Gemini provider can run with
just the OpenAI/Anthropic SDKs installed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from app.llm.models import (
    ChatResult,
    EmbedResult,
    LLMMessage,
    LLMUsage,
    MessageRole,
    ToolDefinition,
)
from app.llm.pricing import estimate_cost


def _role(role: MessageRole) -> str:
    return {
        MessageRole.SYSTEM: "model",  # Gemini has no system role; handled separately
        MessageRole.USER: "user",
        MessageRole.ASSISTANT: "model",
        MessageRole.TOOL: "tool",
    }[role]


class GeminiClient:
    """Chat + embeddings via Google's Generative AI SDK."""

    def __init__(self, *, model: str, api_key: str | None, http: Any = None) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        from google import genai
        from google.genai import types

        self._genai = genai
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self.model = model

    @property
    def provider(self) -> str:
        return "gemini"

    def _build_contents(self, messages: list[LLMMessage]) -> list[Any]:
        contents: list[Any] = []
        for m in messages:
            if m.role is MessageRole.SYSTEM:
                contents.append(
                    self._types.Content(role="user", parts=[self._types.PartFromText(m.content)])
                )
                continue
            contents.append(
                self._types.Content(role=_role(m.role), parts=[self._types.PartFromText(m.content)])
            )
        return contents

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[ChatResult]:
        config: dict[str, Any] = {}
        if temperature is not None:
            config["temperature"] = temperature
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens
        if tools:
            declaration = cast("Any", self._types.FunctionDeclaration)
            tool = cast("Any", self._types.Tool)
            config["tools"] = [
                tool(
                    function=declaration(
                        name=t.name,
                        description=t.description,
                        parameters=t.parameters,
                    )
                )
                for t in tools
            ]

        if stream:
            return self._stream(messages, config)

        contents = self._build_contents(messages)
        resp = await self._client.aio.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._types.GenerateContentConfig(**config) if config else None,
        )
        usage = resp.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        return ChatResult(
            text=resp.text or "",
            usage=LLMUsage(
                provider=self.provider,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=estimate_cost(self.provider, self.model, input_tokens, output_tokens),
            ),
            model=self.model,
            finish_reason=resp.candidates[0].finish_reason.name if resp.candidates else "",
            response_id=resp.name,
        )

    async def _stream(
        self, messages: list[LLMMessage], config: dict[str, Any]
    ) -> AsyncIterator[ChatResult]:
        contents = self._build_contents(messages)
        stream = await self._client.aio.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=self._types.GenerateContentConfig(**config) if config else None,
        )
        buffer: str = ""
        async for chunk in stream:
            text = chunk.text or ""
            if text:
                buffer += text
                yield ChatResult(
                    text=text,
                    usage=LLMUsage(
                        provider=self.provider,
                        model=self.model,
                        input_tokens=0,
                        output_tokens=0,
                        cost_usd=0.0,
                    ),
                    model=self.model,
                    finish_reason="",
                )
        yield ChatResult(
            text="",
            usage=LLMUsage(
                provider=self.provider,
                model=self.model,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
            ),
            model=self.model,
            finish_reason="stop",
        )

    async def embeddings(self, inputs: list[str]) -> EmbedResult:
        raise NotImplementedError("Use the dedicated embeddings endpoint for Gemini")
