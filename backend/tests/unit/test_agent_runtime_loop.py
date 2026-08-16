"""Unit tests for the M5 agent runtime executor lifecycle.

Covers the guarded run loop in ``app/agents/runtime.py``: executor resolution
(no executor -> run fails), claiming (concurrent claim -> skip), the timeout
budget, success/failure landing, cancel-flag honouring, exception sanitization,
and goal extraction. ``AgentService`` is mocked; no database is involved.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.agents.runtime as runtime_mod
from app.agents.executors import ExecutorContext, ExecutorResult
from app.agents.runtime import AgentRuntime
from app.core.errors import AppError
from app.models.agent_run import AgentRun
from app.models.enums import AgentRunStatus, AgentRunTrigger

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000202")


def _run(
    *,
    status: AgentRunStatus = AgentRunStatus.QUEUED,
    agent_name: str = "founder_assistant",
    input_: dict | None = None,
) -> AgentRun:
    return AgentRun(
        id=RUN_ID,
        organization_id=ORG_ID,
        agent_name=agent_name,
        status=status,
        trigger=AgentRunTrigger.MANUAL,
        input=input_ or {},
    )


class _RecordingExecutor:
    """Minimal protocol-fulfilling executor that records its context."""

    name = "founder_assistant"
    description = "test executor"

    def __init__(self, result: ExecutorResult | None = None, raise_exc=None) -> None:
        self.seen: ExecutorContext | None = None
        self._result = result
        self._raise_exc = raise_exc

    async def execute(self, ctx: ExecutorContext) -> ExecutorResult:
        self.seen = ctx
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._result or ExecutorResult(success=True)


def _make_service(**overrides) -> AsyncMock:
    service = AsyncMock()
    service.start_run = AsyncMock(return_value=_run(status=AgentRunStatus.RUNNING))
    service.complete_run = AsyncMock(return_value=_run(status=AgentRunStatus.SUCCEEDED))
    service.fail_run = AsyncMock(return_value=_run(status=AgentRunStatus.FAILED))
    service.fail_queued_run = AsyncMock(return_value=_run(status=AgentRunStatus.FAILED))
    for name, value in overrides.items():
        setattr(service, name, value)
    return service


@pytest.fixture(autouse=True)
def _ai_kill_switch_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op the per-org AI kill switch for runtime-loop lifecycle tests.

    The kill switch is enforced inside ``execute_run`` but is exercised in full
    by the dedicated kill-switch tests; these tests focus on the run-loop
    lifecycle and therefore disable it (AI enabled) so the loop proceeds.
    """

    async def _noop(self: object, org_id: object) -> None:
        return None

    monkeypatch.setattr("app.services.ai_service.AIService.assert_ai_enabled", _noop)


@patch.object(runtime_mod, "AgentService")
@pytest.mark.asyncio
async def test_execute_run_success_lands_succeeded(agent_service) -> None:
    service = _make_service()
    agent_service.return_value = service
    executor = _RecordingExecutor(
        ExecutorResult(success=True, output={"summary": "ok"}, cost=Decimal("0.01"))
    )
    runtime = AgentRuntime(resolve_executor=lambda name: executor)

    result = await runtime.execute_run(None, _run(input_={"goal": "research_lead"}))

    assert result.status is AgentRunStatus.SUCCEEDED
    service.start_run.assert_awaited_once_with(ORG_ID, RUN_ID)
    service.complete_run.assert_awaited_once()
    assert service.complete_run.await_args.args[:2] == (ORG_ID, RUN_ID)
    assert service.complete_run.await_args.kwargs["output"] == {"summary": "ok"}
    assert service.complete_run.await_args.kwargs["cost"] == Decimal("0.01")


@patch.object(runtime_mod, "AgentService")
@pytest.mark.asyncio
async def test_execute_run_passes_goal_to_executor(agent_service) -> None:
    service = _make_service()
    agent_service.return_value = service
    executor = _RecordingExecutor()
    runtime = AgentRuntime(resolve_executor=lambda name: executor)

    await runtime.execute_run(None, _run(input_={"goal": "research_lead"}))

    assert executor.seen is not None
    assert executor.seen.goal == "research_lead"
    assert executor.seen.organization_id == ORG_ID
    assert executor.seen.run_id == RUN_ID


@patch.object(runtime_mod, "AgentService")
@pytest.mark.asyncio
async def test_execute_run_failure_lands_failed(agent_service) -> None:
    service = _make_service()
    agent_service.return_value = service
    executor = _RecordingExecutor(
        ExecutorResult(success=False, error="research API unreachable")
    )
    runtime = AgentRuntime(resolve_executor=lambda name: executor)

    result = await runtime.execute_run(None, _run())

    assert result.status is AgentRunStatus.FAILED
    service.fail_run.assert_awaited_once_with(ORG_ID, RUN_ID, error="research API unreachable")


@patch.object(runtime_mod, "AgentService")
@pytest.mark.asyncio
async def test_execute_run_no_executor_fails_queued_run(agent_service) -> None:
    service = _make_service()
    agent_service.return_value = service
    runtime = AgentRuntime(resolve_executor=lambda name: None)

    result = await runtime.execute_run(None, _run(agent_name="research_agent"))

    assert result.status is AgentRunStatus.FAILED
    service.fail_queued_run.assert_awaited_once()
    error = service.fail_queued_run.await_args.kwargs["error"]
    assert "no registered executor" in error


@patch.object(runtime_mod, "AgentService")
@pytest.mark.asyncio
async def test_execute_run_skips_when_concurrently_claimed(agent_service) -> None:
    service = _make_service(
        start_run=AsyncMock(
            side_effect=AppError("agent_run.invalid_state", "claimed", 409)
        )
    )
    agent_service.return_value = service
    executor = _RecordingExecutor()
    runtime = AgentRuntime(resolve_executor=lambda name: executor)

    result = await runtime.execute_run(None, _run())

    assert result is None
    assert executor.seen is None


@patch.object(runtime_mod, "AgentService")
@pytest.mark.asyncio
async def test_execute_run_timeout_lands_failed(agent_service) -> None:
    service = _make_service()
    agent_service.return_value = service

    class _SlowExecutor:
        name = "founder_assistant"
        description = "slow"

        async def execute(self, ctx: ExecutorContext) -> ExecutorResult:
            await asyncio.sleep(10)
            return ExecutorResult(success=True)

    runtime = AgentRuntime(resolve_executor=lambda name: _SlowExecutor())
    with patch.object(runtime_mod, "settings", SimpleNamespace(AGENT_RUN_TIMEOUT_SECONDS=0.05)):
        result = await runtime.execute_run(None, _run())

    assert result.status is AgentRunStatus.FAILED
    assert service.fail_run.await_args.kwargs["error"] == "Agent run exceeded its time budget"


@patch.object(runtime_mod, "AgentService")
@pytest.mark.asyncio
async def test_execute_run_sanitizes_unexpected_exception(agent_service) -> None:
    service = _make_service()
    agent_service.return_value = service
    executor = _RecordingExecutor(raise_exc=RuntimeError("boom"))
    runtime = AgentRuntime(resolve_executor=lambda name: executor)

    result = await runtime.execute_run(None, _run())

    assert result.status is AgentRunStatus.FAILED
    error = service.fail_run.await_args.kwargs["error"]
    assert error == "boom"
    assert "Traceback" not in error


@patch.object(runtime_mod, "AgentService")
@pytest.mark.asyncio
async def test_execute_run_returns_none_when_concurrently_finalised(agent_service) -> None:
    service = _make_service(
        complete_run=AsyncMock(
            side_effect=AppError("agent_run.illegal_transition", "done already", 409)
        )
    )
    agent_service.return_value = service
    executor = _RecordingExecutor(ExecutorResult(success=True))
    runtime = AgentRuntime(resolve_executor=lambda name: executor)

    result = await runtime.execute_run(None, _run())

    assert result is None
