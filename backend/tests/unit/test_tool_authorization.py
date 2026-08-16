"""M11-A: per-tool authorization + goal-scoped allow-list enforcement.

Exercises the authorization primitives directly and through the Brain tool
loop, including a prompt-injection attempt that tries to call a tool outside
the goal's allow-list.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.ai.brain import Brain
from app.ai.planner import allowed_tools_for_goal
from app.core.permissions import Permission
from app.llm.models import ChatResult, LLMUsage, ToolCall
from app.llm.providers import ProviderClient
from app.llm.service import LLMService
from app.models.lead import Lead
from app.tools.base import ToolResult
from app.tools.registry import (
    ToolAuthorizationError,
    ToolRegistry,
    assert_can_invoke_tool,
    required_permission_for,
)

LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _lead() -> Lead:
    lead = Lead(
        organization_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        first_name="Ada",
        last_name="Lovelace",
        company="Analytical",
        position="Engineer",
        email="ada@example.com",
    )
    lead.id = LEAD_ID
    return lead


def _usage() -> LLMUsage:
    return LLMUsage("openai", "gpt-4o-mini", 10, 5, 0.001)


class _NamedTool:
    """A registered tool that echoes its name; records its call."""

    def __init__(self, name: str, result: ToolResult | None = None) -> None:
        self.name = name
        self.description = f"tool {name}"
        self.parameters: dict[str, Any] = {"type": "object", "properties": {}}
        self.result = result or ToolResult(ok=True, content={"ok": 1})
        self.calls: list[dict[str, Any]] = []

    async def run(self, input: dict[str, Any]) -> ToolResult:
        self.calls.append(input)
        return self.result


class _ScriptedClient(ProviderClient):
    def __init__(self, script: list[ChatResult]) -> None:
        self._script = list(script)

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return "gpt-4o-mini"

    async def chat(self, messages, *, tools=None, temperature=None, max_tokens=None, stream=False):
        return self._script.pop(0)


def _registry_with(*names: str) -> ToolRegistry:
    reg = ToolRegistry()
    for n in names:
        reg.register(_NamedTool(n))
    return reg


def _one_tool_call(client: _ScriptedClient, name: str) -> list[ChatResult]:
    return [
        ChatResult(
            "",
            _usage(),
            "gpt-4o-mini",
            "tool_calls",
            tool_calls=[ToolCall(id="call_1", name=name, arguments=json.dumps({"x": 1}))],
        ),
        ChatResult("final answer", _usage(), "gpt-4o-mini", "stop"),
    ]


# --- authorization primitives ------------------------------------------------


def test_assert_can_invoke_allows_when_permitted() -> None:
    perms = frozenset({Permission.LEAD_READ})
    assert assert_can_invoke_tool(perms, "lead_search") is None


def test_assert_can_invoke_denies_when_missing() -> None:
    perms = frozenset({Permission.AI_RUN})
    with pytest.raises(ToolAuthorizationError):
        assert_can_invoke_tool(perms, "lead_search")


def test_assert_can_invoke_denies_unknown_tool() -> None:
    perms = frozenset({Permission.LEAD_READ})
    with pytest.raises(ToolAuthorizationError):
        assert_can_invoke_tool(perms, "does_not_exist")


def test_required_permission_reflects_manifest() -> None:
    assert required_permission_for("n8n_dispatch") is Permission.LEAD_WRITE
    assert required_permission_for("intelligence_signals") is Permission.INTELLIGENCE_READ
    assert required_permission_for("ghost") is None


# --- goal allow-list ---------------------------------------------------------


def test_known_goal_allowlist_is_bounded() -> None:
    tools = allowed_tools_for_goal("dispatch_outreach")
    assert "n8n_dispatch" in tools
    assert "lead_search" in tools
    # read-only-only tools that are not needed for this goal stay out
    assert "growth_analysis" not in tools


def test_unknown_goal_falls_back_to_read_only() -> None:
    tools = allowed_tools_for_goal("totally_made_up")
    assert "n8n_dispatch" not in tools
    assert "lead_search" in tools
    assert "intelligence_signals" in tools


# --- brain loop enforcement --------------------------------------------------


@pytest.mark.asyncio
async def test_brain_allows_authorized_tool_in_allowlist() -> None:
    reg = _registry_with("lead_search")
    client = _ScriptedClient(_one_tool_call(_ScriptedClient, "lead_search"))
    brain = Brain(LLMService(client), reg)
    result = await brain.run(
        goal="research_lead",
        lead=_lead(),
        research=None,
        caller_permissions=frozenset({Permission.LEAD_READ}),
        allowed_tools={"lead_search"},
    )
    assert result.success is True
    assert result.tool_results and result.tool_results[0].ok is True
    assert result.tool_trace and result.tool_trace[0]["authorized"] is True


@pytest.mark.asyncio
async def test_brain_denies_tool_without_permission() -> None:
    reg = _registry_with("lead_search")
    client = _ScriptedClient(_one_tool_call(_ScriptedClient, "lead_search"))
    brain = Brain(LLMService(client), reg)
    # Has AI_RUN but NOT LEAD_READ -> lead_search must be denied.
    result = await brain.run(
        goal="research_lead",
        lead=_lead(),
        research=None,
        caller_permissions=frozenset({Permission.AI_RUN}),
        allowed_tools={"lead_search"},
    )
    assert result.success is True  # run recovers and finishes
    assert result.tool_results and result.tool_results[0].ok is False
    assert "permission" in (result.tool_results[0].error or "").lower()
    assert result.tool_trace and result.tool_trace[0]["authorized"] is False


@pytest.mark.asyncio
async def test_brain_denies_tool_outside_goal_allowlist_prompt_injection() -> None:
    # A prompt-injection attempt to call n8n_dispatch during a research goal.
    reg = _registry_with("n8n_dispatch")
    client = _ScriptedClient(_one_tool_call(_ScriptedClient, "n8n_dispatch"))
    brain = Brain(LLMService(client), reg)
    # The actor even HAS the dispatch permission, but the goal allow-list must
    # still forbid it.
    result = await brain.run(
        goal="research_lead",
        lead=_lead(),
        research=None,
        caller_permissions=frozenset({Permission.LEAD_WRITE}),
        allowed_tools=allowed_tools_for_goal("research_lead"),
    )
    assert result.tool_results and result.tool_results[0].ok is False
    assert "not permitted for goal" in (result.tool_results[0].error or "")
    assert result.tool_trace and result.tool_trace[0]["allowed"] is False


@pytest.mark.asyncio
async def test_brain_denies_unknown_tool_in_loop() -> None:
    reg = ToolRegistry()
    client = _ScriptedClient(_one_tool_call(_ScriptedClient, "phantom"))
    brain = Brain(LLMService(client), reg)
    result = await brain.run(
        goal="research_lead",
        lead=_lead(),
        research=None,
        caller_permissions=frozenset({Permission.LEAD_READ}),
        allowed_tools={"phantom"},
    )
    assert result.tool_results and result.tool_results[0].ok is False
    assert "unknown tool" in (result.tool_results[0].error or "")
