"""OpenAI-compatible provider client (Ollama, DeepSeek, self-hosted, etc.).

Uses :mod:`httpx` directly against any endpoint that speaks the OpenAI
Completions/Embeddings wire format — no SDK required, so new compatible
providers need zero added dependencies. The ``kind`` field records the
human-friendly provider name for usage accounting.
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
    ToolCall,
    ToolDefinition,
)
from app.llm.pricing import estimate_cost
from app.llm.providers import _build_http_options


def _message(message: LLMMessage) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": message.role.value, "content": message.content}
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


class OpenAICompatibleClient:
    """OpenAI-format HTTP client for compatible providers."""

    def __init__(
        self,
        *,
        kind: str,
        model: str,
        api_key: str | None,
        base_url: str | None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url:
            raise ValueError(f"{kind} requires a base_url")
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(**_build_http_options())
        self._api_key = api_key
        self._kind = kind
        self.model = model

    @property
    def provider(self) -> str:
        return self._kind

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[ChatResult]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_message(m) for m in messages],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [_tool(t) for t in tools]
        if stream:
            payload["stream"] = True

        resp = await self._http.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {}) or {}
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        message_data = data["choices"][0]["message"]
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", ""),
            )
            for tc in (message_data.get("tool_calls") or [])
            if tc.get("type") == "function"
        ]
        return ChatResult(
            text=message_data.get("content") or "",
            usage=LLMUsage(
                provider=self.provider,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=estimate_cost(self.provider, self.model, input_tokens, output_tokens),
            ),
            model=data.get("model", self.model),
            finish_reason=data["choices"][0].get("finish_reason", ""),
            tool_calls=tool_calls,
            response_id=data.get("id", ""),
        )

    async def embeddings(self, inputs: list[str]) -> EmbedResult:
        resp = await self._http.post(
            f"{self._base_url}/embeddings",
            headers=self._headers(),
            json={"model": self.model, "input": inputs},
        )
        resp.raise_for_status()
        data = resp.json()
        vectors = [item["embedding"] for item in data["data"]]
        usage = data.get("usage", {}) or {}
        input_tokens = usage.get("prompt_tokens", 0)
        return EmbedResult(
            vectors=vectors,
            usage=LLMUsage(
                provider=self.provider,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=0,
                cost_usd=estimate_cost(self.provider, self.model, input_tokens, 0),
            ),
            model=data.get("model", self.model),
        )
