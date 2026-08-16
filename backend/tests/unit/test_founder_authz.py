"""F-SEC-2 / F-SEC-3: founder tool authorization + per-org AI kill switch.

DB-free tests proving:
* the 4 founder-native tools are registered and require the right permission,
* the founder_assistant goal allow-list is bounded (prompt-injection safe),
* the FounderAssistantExecutor routes execution through the SAME M11
  authorization primitive (caller_permissions + goal allow-list),
* the per-org kill switch blocks founder execution, the worker run path, and
  founder proposal execution (fail closed).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.agents.executors.base import ExecutorContext
from app.ai.brain import BrainResult
from app.core.config import settings
from app.core.errors import AppError
from app.core.permissions import Permission, permissions_for_role
from app.models.enums import UserRole
from app.tools.registry import (
    ToolAuthorizationError,
    ToolRegistry,
    assert_can_invoke_tool,
    is_side_effecting,
    required_permission_for,
)

FOUNDER_TOOLS = {
    "summarize_context": Permission.FOUNDER_READ,
    "get_recent_activity": Permission.FOUNDER_READ,
    "create_task": Permission.FOUNDER_MANAGE,
    "propose_founder_action": Permission.FOUNDER_MANAGE,
}
FOUNDER_ASSISTANT_ALLOWLIST = {
    "summarize_context",
    "get_recent_activity",
    "create_task",
    "propose_founder_action",
    "growth_analysis",
    "lead_search",
    "draft_outreach",
}


def test_founder_tools_registered_in_manifest() -> None:
    for name, perm in FOUNDER_TOOLS.items():
        assert required_permission_for(name) == perm
        # create_task / propose_founder_action are side-effecting; the read tools are not
        if perm == Permission.FOUNDER_MANAGE:
            assert is_side_effecting(name) is True
        else:
            assert is_side_effecting(name) is False


def test_founder_assistant_allowlist() -> None:
    from app.ai.planner import allowed_tools_for_goal

    assert allowed_tools_for_goal("founder_assistant") == FOUNDER_ASSISTANT_ALLOWLIST


def test_founder_allowlist_excludes_non_founder_tools() -> None:
    from app.ai.planner import allowed_tools_for_goal

    allow = allowed_tools_for_goal("founder_assistant")
    # Prompt injection cannot reach side-effecting / external tools.
    assert "n8n_dispatch" not in allow
    assert "http_get" not in allow
    assert "web_search" not in allow
    assert "draft_outreach" in allow


def test_founder_tools_authorized_with_founder_permissions() -> None:
    owner_perms = permissions_for_role(UserRole.OWNER)
    for name in FOUNDER_ASSISTANT_ALLOWLIST:
        assert_can_invoke_tool(owner_perms, name)  # must not raise


def test_founder_tools_rejected_without_permission() -> None:
    viewer_perms = permissions_for_role(UserRole.VIEWER)  # FOUNDER_READ only
    # Read-only founder tools are allowed for any viewer that reaches the assistant.
    assert_can_invoke_tool(viewer_perms, "summarize_context")
    assert_can_invoke_tool(viewer_perms, "get_recent_activity")
    # Side-effecting / higher-privilege tools are denied.
    with pytest.raises(ToolAuthorizationError):
        assert_can_invoke_tool(viewer_perms, "create_task")
    with pytest.raises(ToolAuthorizationError):
        assert_can_invoke_tool(viewer_perms, "propose_founder_action")
    with pytest.raises(ToolAuthorizationError):
        assert_can_invoke_tool(viewer_perms, "draft_outreach")
    with pytest.raises(ToolAuthorizationError):
        assert_can_invoke_tool(viewer_perms, "growth_analysis")


def test_unregistered_tool_rejected() -> None:
    owner_perms = permissions_for_role(UserRole.OWNER)
    with pytest.raises(ToolAuthorizationError):
        assert_can_invoke_tool(owner_perms, "not_a_real_tool")


# --- Executor integration (DB-free, Brain + repos monkeypatched) ---


class _User:
    role = UserRole.OWNER


class _FakeUserRepo:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def get(self, uid: Any) -> _User:
        return _User()


class _CaptureBrain:
    captured: dict[str, Any] | None = None

    def __init__(self, llm: Any, registry: ToolRegistry) -> None:
        self._llm = llm
        self._registry = registry

    async def run(
        self,
        *,
        goal: str,
        lead: Any,
        research: Any,
        recent_messages: list[dict[str, Any]] | None = None,
        persona: str | None = None,
        caller_permissions: frozenset[Permission] | None = None,
        allowed_tools: set[str] | None = None,
        organization_id: uuid.UUID | None = None,
        **kw: Any,
    ) -> BrainResult:
        _CaptureBrain.captured = {
            "caller_permissions": caller_permissions,
            "allowed_tools": allowed_tools,
            "organization_id": organization_id,
        }
        return BrainResult(
            success=True,
            response="ok",
            tool_calls=[],
            tool_results=[],
            tool_trace=[],
            steps_taken=0,
            organization_id=organization_id,
            trace_id=None,
            run_id=None,
        )


def _stub_tool_registry(tool_ctx: Any) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(SimpleNamespace(name="summarize_context", description="x", parameters={}))
    return reg


async def test_founder_executor_enforces_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agents.executors.brain_executor import FounderAssistantExecutor
    from app.ai.planner import allowed_tools_for_goal

    monkeypatch.setattr("app.ai.brain.Brain", _CaptureBrain)
    monkeypatch.setattr("app.agents.executors.brain_executor.UserRepository", _FakeUserRepo)
    monkeypatch.setattr("app.tools.founder_tools.founder_registry", _stub_tool_registry)
    async def _fake_build(self: Any) -> SimpleNamespace:
        return SimpleNamespace(summary=lambda: "business context")

    monkeypatch.setattr("app.ai.founder_context.FounderContextBuilder.build", _fake_build)

    def _fake_classify(message: Any) -> SimpleNamespace:
        return SimpleNamespace(
            intent_type=SimpleNamespace(value="status"),
            to_dict=lambda: {},
        )

    monkeypatch.setattr(
        "app.agents.executors.brain_executor.FounderIntentService.classify",
        _fake_classify,
    )

    async def _fake_runtime_deps(self: Any, ctx: Any, client: Any) -> dict[str, Any]:
        return {"llm": object()}

    monkeypatch.setattr(FounderAssistantExecutor, "_runtime_deps", _fake_runtime_deps)
    monkeypatch.setattr(settings, "FOUNDER_ASSISTANT_ENABLED", True)

    async def _kill_switch_enabled(self: Any, org_id: Any) -> None:
        return None  # per-org AI enabled

    monkeypatch.setattr(
        "app.services.ai_service.AIService.assert_ai_enabled", _kill_switch_enabled
    )

    org_id = uuid.uuid4()
    ctx = ExecutorContext(
        session=MagicMock(),
        organization_id=org_id,
        run_id=uuid.uuid4(),
        goal="founder_assistant",
        input={"message": "hi", "actor_user_id": str(uuid.uuid4())},
    )

    executor = FounderAssistantExecutor()
    result = await executor.execute(ctx)

    assert result.success is True
    assert _CaptureBrain.captured is not None
    assert _CaptureBrain.captured["caller_permissions"] is not None
    assert _CaptureBrain.captured["allowed_tools"] == allowed_tools_for_goal("founder_assistant")
    assert _CaptureBrain.captured["organization_id"] == org_id


async def test_founder_executor_kill_switch_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agents.executors.brain_executor import FounderAssistantExecutor

    async def _raise_disabled(self: Any, org_id: Any) -> None:
        raise AppError(code="ai.disabled", message="AI is disabled", status_code=409)

    monkeypatch.setattr("app.services.ai_service.AIService.assert_ai_enabled", _raise_disabled)
    monkeypatch.setattr(settings, "FOUNDER_ASSISTANT_ENABLED", True)

    # No LLM/context wiring needed: the kill switch is checked before any of it.
    ctx = ExecutorContext(
        session=MagicMock(),
        organization_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        goal="founder_assistant",
        input={"message": "hi", "actor_user_id": str(uuid.uuid4())},
    )
    executor = FounderAssistantExecutor()
    result = await executor.execute(ctx)
    assert result.success is False
    assert "disabled" in (result.error or "").lower()


async def test_runtime_kill_switch_blocks_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agents.runtime import AgentRuntime

    class _FakeRun:
        organization_id = uuid.uuid4()
        agent_name = "ai_brain"
        id = uuid.uuid4()
        input: dict[str, Any] = {"goal": "founder_assistant"}

    class _FakeAgentService:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def fail_queued_run(self, org_id: Any, run_id: Any, *, error: str) -> str:
            return "failed"

    monkeypatch.setattr("app.agents.runtime.AgentService", _FakeAgentService)

    async def _raise_disabled(self: Any, org_id: Any) -> None:
        raise AppError(code="ai.disabled", message="disabled", status_code=409)

    monkeypatch.setattr("app.services.ai_service.AIService.assert_ai_enabled", _raise_disabled)

    rt = AgentRuntime()
    result = await rt.execute_run(MagicMock(), _FakeRun())
    assert result == "failed"


async def test_decide_proposal_blocked_by_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.enums import FounderProposalStatus
    from app.services.founder_action_service import FounderActionService

    class _FakeProposal:
        proposal_status = FounderProposalStatus.PROPOSED
        expires_at = None
        approval_request_id = 1

    svc = FounderActionService(MagicMock())

    async def _fake_get(org_id: Any, pid: Any) -> _FakeProposal:
        return _FakeProposal()

    monkeypatch.setattr(svc, "get_proposal", _fake_get)

    async def _raise_disabled(self: Any, org_id: Any) -> None:
        raise AppError(code="ai.disabled", message="disabled", status_code=409)

    monkeypatch.setattr("app.services.ai_service.AIService.assert_ai_enabled", _raise_disabled)

    with pytest.raises(AppError) as exc:
        await svc.decide_proposal(
            uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), approve=True
        )
    assert exc.value.code == "ai.disabled"
