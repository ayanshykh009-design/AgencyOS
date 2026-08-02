"""OpenAI provider client (OpenAI SDK).

Also serves OpenAI-compatible endpoints when a ``base_url`` is supplied through
the generic client — OpenAI is the default provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.models import (
    ChatResult,
    EmbedResult,
    LLMMessage,
    LLMUsage,
    MessageRole,
    ToolCall,
    ToolDefinition,
)
from app.llm.pricing import estimate_cost


def _to_role(role: MessageRole) -> str:
    return {
        MessageRole.SYSTEM: "system",
        MessageRole.USER: "user",
        MessageRole.ASSISTANT: "assistant",
        MessageRole.TOOL: "tool",
    }[role]


def _message(message: LLMMessage) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": _to_role(message.role), "content": message.content}
    if message.name:
        msg["name"] = message.name
    if message.tool_call_id:
        msg["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            }
            for tc in message.tool_calls
        ]
    return msg


def _tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class OpenAIClient:
    """Chat + embeddings via the OpenAI SDK (or a compatible base_url)."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        from openai import AsyncOpenAI

        if not api_key:
            raise ValueError("OpenAI API key is required")
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=http)
        self.model = model

    @property
    def provider(self) -> str:
        return "openai"

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[ChatResult]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [_message(m) for m in messages],
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = [_tool(t) for t in tools]

        if stream:
            return self._stream(kwargs)

        resp = await self._client.chat.completions.create(**kwargs)
        usage = LLMUsage(
            provider=self.provider,
            model=self.model,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            cost_usd=estimate_cost(
                self.provider, self.model, resp.usage.prompt_tokens, resp.usage.completion_tokens
            ),
        )
        choice = resp.choices[0]
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (choice.message.tool_calls or [])
        ]
        return ChatResult(
            text=choice.message.content or "",
            usage=usage,
            model=resp.model,
            finish_reason=choice.finish_reason or "",
            tool_calls=tool_calls,
            response_id=resp.id,
        )

    async def _stream(self, kwargs: dict[str, Any]) -> AsyncIterator[ChatResult]:
        stream = await self._client.chat.completions.create(stream=True, **kwargs)
        buffer: str = ""
        final_usage: LLMUsage | None = None
        async for chunk in stream:
            # The SDK populates per-chunk token usage only on the final chunk.
            if chunk.usage:
                final_usage = LLMUsage(
                    provider=self.provider,
                    model=self.model,
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                    cost_usd=estimate_cost(
                        self.provider,
                        self.model,
                        chunk.usage.prompt_tokens,
                        chunk.usage.completion_tokens,
                    ),
                )
            for choice in chunk.choices:
                delta = choice.delta.content or ""
                finish = choice.finish_reason
                if delta:
                    buffer += delta
                    yield ChatResult(
                        text=delta,
                        usage=LLMUsage(
                            provider=self.provider,
                            model=self.model,
                            input_tokens=0,
                            output_tokens=0,
                            cost_usd=0.0,
                        ),
                        model=self.model,
                        finish_reason=finish or "",
                    )
        yield ChatResult(
            text="",
            usage=final_usage
            or LLMUsage(
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
        resp = await self._client.embeddings.create(model=self.model, input=inputs)
        vectors = [data.embedding for data in resp.data]
        total = resp.usage.prompt_tokens
        return EmbedResult(
            vectors=vectors,
            usage=LLMUsage(
                provider=self.provider,
                model=self.model,
                input_tokens=total,
                output_tokens=0,
                cost_usd=estimate_cost(self.provider, self.model, total, 0),
            ),
            model=resp.model,
        )
