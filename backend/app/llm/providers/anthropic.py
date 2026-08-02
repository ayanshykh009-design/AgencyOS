"""Anthropic provider client (Claude messages API via the Anthropic SDK)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

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


def _role(role: MessageRole) -> str:
    if role is MessageRole.SYSTEM:
        return "user"
    return {
        MessageRole.USER: "user",
        MessageRole.ASSISTANT: "assistant",
        MessageRole.TOOL: "user",
    }[role]


def _load_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


def _content(message: LLMMessage) -> str | list[dict[str, Any]]:
    if message.tool_calls:
        blocks: list[dict[str, Any]] = []
        if message.content:
            blocks.append({"type": "text", "text": message.content})
        for tc in message.tool_calls:
            blocks.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": _load_json(tc.arguments),
                }
            )
        return blocks
    if message.tool_call_id:
        return [
            {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
        ]
    return message.content


def _to_anthropic(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    return [{"role": _role(m.role), "content": _content(m)} for m in messages]


def _tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


class AnthropicClient:
    """Chat completions via Anthropic's messages API."""

    def __init__(self, *, model: str, api_key: str | None, http: Any = None) -> None:
        from anthropic import AsyncAnthropic

        if not api_key:
            raise ValueError("Anthropic API key is required")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if http is not None:
            kwargs["http_client"] = http
        self._client = AsyncAnthropic(**kwargs)
        self.model = model

    @property
    def provider(self) -> str:
        return "anthropic"

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[ChatResult]:
        system = "".join(m.content for m in messages if m.role is MessageRole.SYSTEM)
        convo = [m for m in messages if m.role is not MessageRole.SYSTEM]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": _to_anthropic(convo),
            "max_tokens": max_tokens or 4096,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = _tools(tools)

        if stream:
            return self._stream(kwargs, system)

        resp = await self._client.messages.create(system=system or "", **kwargs)
        in_tokens = int(resp.usage.input_tokens or 0)
        out_tokens = int(resp.usage.output_tokens or 0)
        usage = LLMUsage(
            provider=self.provider,
            model=self.model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            cost_usd=estimate_cost(
                self.provider,
                self.model,
                in_tokens,
                out_tokens,
            ),
        )
        text = ""
        tool_calls: list[ToolCall] = []
        for content in resp.content:
            if content.type == "text":
                text += content.text
            elif content.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=content.id,
                        name=content.name,
                        arguments=content.input,
                    )
                )
        return ChatResult(
            text=text,
            usage=usage,
            model=resp.model,
            finish_reason=resp.stop_reason or "",
            tool_calls=tool_calls,
            response_id=resp.id,
        )

    async def _stream(self, kwargs: dict[str, Any], system: str) -> AsyncIterator[ChatResult]:
        stream = await self._client.messages.create(system=system or "", stream=True, **kwargs)
        buffer: str = ""
        final_usage: LLMUsage | None = None
        async for event in stream:
            if event.type == "message_delta":
                if event.usage:
                    in_tokens = int(event.usage.input_tokens or 0)
                    out_tokens = int(event.usage.output_tokens or 0)
                    final_usage = LLMUsage(
                        provider=self.provider,
                        model=self.model,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        cost_usd=estimate_cost(
                            self.provider,
                            self.model,
                            in_tokens,
                            out_tokens,
                        ),
                    )
            elif event.type == "content_block_delta":
                delta = event.delta.text or ""
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
                        finish_reason=event.delta.stop_reason or "",
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
        raise NotImplementedError("Anthropic does not expose an embeddings API")
