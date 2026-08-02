"""Unit tests for LLM provider wire-format translation (tool calling).

These exercise the message → API-payload translation and the response parsing
for the Anthropic, OpenAI-compatible, and Gemini providers. Network access is
never performed: SDK-backed clients are built via ``__new__`` with fake
transports, and HTTP-backed clients use ``httpx.MockTransport``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx

from app.llm.models import (
    ChatResult,
    LLMMessage,
    MessageRole,
    ToolCall,
    ToolDefinition,
)
from app.llm.providers import anthropic as anthropic_mod
from app.llm.providers import gemini as gemini_mod
from app.llm.providers import openai_compatible as openai_compat_mod


def _tool_defs() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="web_search",
            description="Search the web",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        )
    ]


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def test_anthropic_role_mapping() -> None:
    assert anthropic_mod._role(MessageRole.TOOL) == "user"
    assert anthropic_mod._role(MessageRole.USER) == "user"
    assert anthropic_mod._role(MessageRole.ASSISTANT) == "assistant"
    assert anthropic_mod._role(MessageRole.SYSTEM) == "user"


def test_anthropic_assistant_tool_calls_serialize_as_tool_use() -> None:
    msg = LLMMessage(
        role=MessageRole.ASSISTANT,
        content="",
        tool_calls=[ToolCall(id="call_1", name="web_search", arguments='{"query": "x"}')],
    )
    content = anthropic_mod._content(msg)
    assert content == [
        {
            "type": "tool_use",
            "id": "call_1",
            "name": "web_search",
            "input": {"query": "x"},
        }
    ]


def test_anthropic_tool_result_serializes_with_tool_use_id() -> None:
    msg = LLMMessage(
        role=MessageRole.TOOL,
        content="ok",
        tool_call_id="call_1",
    )
    content = anthropic_mod._content(msg)
    assert content == [{"type": "tool_result", "tool_use_id": "call_1", "content": "ok"}]


def test_anthropic_tool_use_keeps_raw_arguments_when_not_json() -> None:
    msg = LLMMessage(
        role=MessageRole.ASSISTANT,
        content="",
        tool_calls=[ToolCall(id="call_1", name="f", arguments="not-json")],
    )
    content = anthropic_mod._content(msg)
    assert content[0]["input"] == "not-json"


async def test_anthropic_chat_parses_tool_use_response() -> None:
    class _FakeMessages:
        def __init__(self, response: Any) -> None:
            self._response = response
            self.sent: dict[str, Any] = {}

        async def create(self, **kwargs: Any) -> Any:
            self.sent = kwargs
            return self._response

    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="tool_use", id="call_1", name="web_search", input={"query": "x"}),
            SimpleNamespace(type="text", text="looking it up"),
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        model="claude-3-5-sonnet",
        stop_reason="tool_use",
        id="msg_123",
    )

    client = anthropic_mod.AnthropicClient.__new__(anthropic_mod.AnthropicClient)
    fake = _FakeMessages(response)
    client._client = SimpleNamespace(messages=fake)
    client.model = "claude-3-5-sonnet"

    result = await client.chat([LLMMessage(MessageRole.USER, "hi")], tools=_tool_defs())
    assert isinstance(result, ChatResult)
    assert [tc.name for tc in result.tool_calls] == ["web_search"]
    assert result.tool_calls[0].arguments == {"query": "x"}
    assert result.text == "looking it up"
    assert fake.sent["tools"][0]["name"] == "web_search"
    assert fake.sent["messages"][0]["role"] == "user"


# ---------------------------------------------------------------------------
# OpenAI-compatible
# ---------------------------------------------------------------------------


def test_openai_compatible_tool_message_serialization() -> None:
    tool_msg = LLMMessage(role=MessageRole.TOOL, content="ok", tool_call_id="call_1")
    assert openai_compat_mod._message(tool_msg) == {
        "role": "tool",
        "content": "ok",
        "tool_call_id": "call_1",
    }

    assistant_msg = LLMMessage(
        role=MessageRole.ASSISTANT,
        content="",
        tool_calls=[ToolCall(id="call_1", name="web_search", arguments='{"query": "x"}')],
    )
    assert openai_compat_mod._message(assistant_msg) == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "web_search", "arguments": '{"query": "x"}'},
            }
        ],
    }


async def test_openai_compatible_chat_parses_tool_calls() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": "compat-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "web_search", "arguments": '{"q":"x"}'},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            },
        )

    client = openai_compat_mod.OpenAICompatibleClient(
        kind="deepseek",
        model="deepseek-chat",
        api_key=None,
        base_url="https://compat.example.com",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await client.chat(
        [LLMMessage(MessageRole.USER, "hi")],
        tools=_tool_defs(),
    )
    assert isinstance(result, ChatResult)
    assert [tc.name for tc in result.tool_calls] == ["web_search"]
    assert result.tool_calls[0].arguments == '{"q":"x"}'
    payload = captured["payload"]
    assert '"tools"' in payload
    assert '"web_search"' in payload


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


def _gemini_client() -> gemini_mod.GeminiClient:
    from google.genai import types

    client = gemini_mod.GeminiClient.__new__(gemini_mod.GeminiClient)
    client._types = types
    client.model = "gemini-2.0-flash"
    return client


def test_gemini_contents_serialize_tool_call_and_result() -> None:
    client = _gemini_client()
    messages = [
        LLMMessage(MessageRole.SYSTEM, "be terse"),
        LLMMessage(
            MessageRole.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="call_1", name="web_search", arguments='{"query": "x"}')],
        ),
        LLMMessage(MessageRole.TOOL, content="ok", tool_call_id="call_1"),
    ]
    contents = [c.to_json_dict() for c in client._build_contents(messages)]
    assert [c["role"] for c in contents] == ["model", "user"]
    assert contents[0]["parts"][0]["function_call"]["name"] == "web_search"
    assert contents[0]["parts"][0]["function_call"]["args"] == {"query": "x"}
    assert contents[1]["parts"][0]["function_response"]["name"] == "web_search"
    assert contents[1]["parts"][0]["function_response"]["response"] == {"output": "ok"}


def test_gemini_parse_function_calls() -> None:
    from google.genai import types

    client = _gemini_client()
    resp = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="lead_search", args={"query": "ada"}, id="fc_0"
                            )
                        )
                    ],
                )
            )
        ]
    )
    tool_calls = client._parse_function_calls(resp)
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "fc_0"
    assert tool_calls[0].name == "lead_search"
    assert tool_calls[0].arguments == '{"query": "ada"}'
