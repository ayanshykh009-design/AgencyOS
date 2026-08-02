"""Unit tests for the AI brain (planner + orchestrator loop).

The brain loop is exercised with a fake LLM client (no network) and a registry
built from fake/stub tools.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.ai.brain import Brain, BrainConfig
from app.ai.planner import Plan, PlanStep, all_known_goals, plan_for_goal
from app.llm.models import ChatResult, LLMMessage, LLMUsage, MessageRole, ToolCall
from app.llm.providers import ProviderClient
from app.llm.service import LLMService
from app.models.lead import Lead
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry

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


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def test_planner_returns_known_plans() -> None:
    goals = all_known_goals()
    assert {"research_lead", "search_leads", "draft_email", "dispatch_outreach"} <= set(goals)
    for goal in goals:
        assert plan_for_goal(goal) is not None


def test_planner_interpolates_params() -> None:
    plan = plan_for_goal("research_lead", lead_id=str(LEAD_ID))
    assert isinstance(plan, Plan)
    assert plan.steps[0].input == {"lead_id": str(LEAD_ID)}


def test_planner_unknown_goal_is_none() -> None:
    assert plan_for_goal("fly_to_mars") is None


def test_planner_first_tool_and_remaining() -> None:
    plan = Plan(goal="g", steps=[PlanStep("a", {}), PlanStep("b", {})])
    assert plan.first_tool() == PlanStep("a", {})
    assert plan.remaining() == [PlanStep("b", {})]
    empty = Plan(goal="g", steps=[])
    assert empty.first_tool() is None


# ---------------------------------------------------------------------------
# Brain
# ---------------------------------------------------------------------------


class _StubTool:
    """Registers a fixed ToolResult; records the arguments it received."""

    name = "stub"
    description = "stub tool"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, result: ToolResult) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def run(self, input: dict[str, Any]) -> ToolResult:
        self.calls.append(input)
        return self._result


class _ScriptedClient(ProviderClient):
    """Provider client that replays a script of ChatResults."""

    def __init__(self, script: list[ChatResult]) -> None:
        self._script = list(script)
        self.messages_seen: list[list[LLMMessage]] = []

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return "gpt-4o-mini"

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        tools=None,
        temperature=None,
        max_tokens=None,
        stream: bool = False,
    ) -> ChatResult:
        self.messages_seen.append(list(messages))
        return self._script.pop(0)


@pytest.mark.asyncio
async def test_brain_returns_text_when_no_tool_calls() -> None:
    client = _ScriptedClient([ChatResult("done", _usage(), "gpt-4o-mini", "stop")])
    registry = ToolRegistry()
    brain = Brain(LLMService(client), registry)

    result = await brain.run(goal="research_lead", lead=_lead(), research=None)

    assert result.success is True
    assert result.response == "done"
    assert result.steps_taken == 1
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_brain_executes_tool_call_and_returns() -> None:
    tool = _StubTool(ToolResult(ok=True, content={"ok": 1}))
    registry = ToolRegistry()
    registry.register(tool)

    client = _ScriptedClient(
        [
            ChatResult(
                "",
                _usage(),
                "gpt-4o-mini",
                "tool_calls",
                tool_calls=[ToolCall(id="call_1", name="stub", arguments=json.dumps({"x": 1}))],
            ),
            ChatResult("final answer", _usage(), "gpt-4o-mini", "stop"),
        ]
    )
    brain = Brain(LLMService(client), registry)

    result = await brain.run(goal="g", lead=_lead(), research=None)

    assert result.success is True
    assert result.response == "final answer"
    assert tool.calls == [{"x": 1}]
    assert result.steps_taken == 2
    # The tool result was appended to the history as a TOOL message.
    last_round = client.messages_seen[-1]
    assert last_round[-1].role == MessageRole.TOOL
    assert last_round[-1].content == '{"ok": 1}'


@pytest.mark.asyncio
async def test_brain_survives_unknown_tool_call() -> None:
    registry = ToolRegistry()
    client = _ScriptedClient(
        [
            ChatResult(
                "",
                _usage(),
                "gpt-4o-mini",
                "tool_calls",
                tool_calls=[ToolCall(id="call_1", name="missing_tool", arguments="{}")],
            ),
            ChatResult("recovered", _usage(), "gpt-4o-mini", "stop"),
        ]
    )
    brain = Brain(LLMService(client), registry)

    result = await brain.run(goal="g", lead=_lead(), research=None)

    assert result.success is True
    assert result.response == "recovered"
    assert result.tool_results and result.tool_results[0].ok is False


@pytest.mark.asyncio
async def test_brain_stops_at_max_steps() -> None:
    tool = _StubTool(ToolResult(ok=True, content="again"))
    registry = ToolRegistry()
    registry.register(tool)

    # Every step requests a tool call, so the loop never terminates on its own.
    client = _ScriptedClient(
        [
            ChatResult(
                "",
                _usage(),
                "gpt-4o-mini",
                "tool_calls",
                tool_calls=[ToolCall(id=f"c{i}", name="stub", arguments="{}")],
            )
            for i in range(3)
        ]
    )
    brain = Brain(LLMService(client), registry, config=BrainConfig(max_steps=2))

    result = await brain.run(goal="g", lead=_lead(), research=None)

    assert result.success is False
    assert "max steps" in (result.error or "")
    assert result.steps_taken == 2


@pytest.mark.asyncio
async def test_brain_returns_error_when_llm_fails() -> None:
    class _FailingClient(ProviderClient):
        @property
        def provider(self) -> str:
            return "openai"

        @property
        def model(self) -> str:
            return "gpt-4o-mini"

        async def chat(
            self, messages, *, tools=None, temperature=None, max_tokens=None, stream=False
        ):
            raise RuntimeError("provider down")

    brain = Brain(LLMService(_FailingClient()), ToolRegistry())
    result = await brain.run(goal="g", lead=_lead(), research=None)

    assert result.success is False
    assert "LLM call failed" in (result.error or "")


@pytest.mark.asyncio
async def test_brain_plan_override_injects_tool_calls() -> None:
    tool = _StubTool(ToolResult(ok=True, content="plan step done"))
    registry = ToolRegistry()
    registry.register(tool)

    client = _ScriptedClient(
        [
            ChatResult(
                "",
                _usage(),
                "gpt-4o-mini",
                "tool_calls",
                tool_calls=[ToolCall(id="plan_0", name="stub", arguments=json.dumps({"n": 1}))],
            ),
            ChatResult("finished", _usage(), "gpt-4o-mini", "stop"),
        ]
    )
    brain = Brain(LLMService(client), registry)

    result = await brain.run_with_plan(goal="g", lead=_lead(), research=None)

    assert result.success is True
    assert tool.calls == [{"n": 1}]


def test_brain_parse_arguments_handles_garbage() -> None:
    assert Brain._parse_arguments("") == {}
    assert Brain._parse_arguments("not json") == {}
    assert Brain._parse_arguments("[1,2]") == {}
    assert Brain._parse_arguments('{"a": 1}') == {"a": 1}
