"""Unit tests: ExecutionWorker sweep logic with a fake session + adapters."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import ExecutionStatus, WorkflowStatus
from app.workers.execution_worker import ExecutionWorker

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000601")


class FakeSession:
    def add(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


class FakeSessionCM:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _execution(**overrides: object) -> MagicMock:
    execution = MagicMock()
    execution.id = EXECUTION_ID
    execution.organization_id = ORG_ID
    execution.workflow_id = WORKFLOW_ID
    execution.status = ExecutionStatus.QUEUED
    execution.input = {"lead_id": "x"}
    execution.attempts = 0
    execution.max_attempts = 3
    for key, value in overrides.items():
        setattr(execution, key, value)
    return execution


def _patch_worker(
    monkeypatch,
    *,
    queued: list | None = None,
    due: list | None = None,
    stuck: list | None = None,
    workflow: MagicMock | None = None,
    adapter_output: dict | None = None,
    adapter_raises: Exception | None = None,
) -> FakeSession:
    session = FakeSession()
    session.committed = False

    def _factory() -> FakeSessionCM:
        return FakeSessionCM(session)

    monkeypatch.setattr("app.workers.execution_worker.async_session_factory", _factory)
    monkeypatch.setattr(
        "app.workers.execution_worker.WorkflowRepository",
        type(
            "W",
            (),
            {
                "__init__": lambda self, s: None,
                "get": lambda self, org_id, workflow_id: AsyncMock(
                    return_value=workflow
                )(),
            },
        ),
    )

    class FakeExecutionService:
        def __init__(self, s) -> None:
            pass

        get_queued = AsyncMock(return_value=queued or [])
        get_queued_for_retry = AsyncMock(return_value=due or [])
        get_stuck_running = AsyncMock(return_value=stuck or [])
        retry = AsyncMock()
        start = AsyncMock(return_value=_execution(status=ExecutionStatus.RUNNING))
        complete = AsyncMock()
        fail = AsyncMock()
        timeout = AsyncMock()

    monkeypatch.setattr(
        "app.workers.execution_worker.WorkflowExecutionService", FakeExecutionService
    )
    monkeypatch.setattr(
        "app.workers.execution_worker.get_adapter",
        lambda mode: MagicMock(
            execute=AsyncMock(
                side_effect=(
                    adapter_raises
                    if adapter_raises
                    else lambda *a, **k: adapter_output or {"ok": True}
                )
            )
        ),
    )
    return session


async def test_process_retries_requeues_due(monkeypatch) -> None:
    session = _patch_worker(monkeypatch, due=[_execution(status=ExecutionStatus.RETRYING)])

    count = await ExecutionWorker.process_retries()

    assert count == 1
    assert session.committed is True


async def test_process_queued_runs_successful_execution(monkeypatch) -> None:
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    session = _patch_worker(
        monkeypatch, queued=[_execution()], workflow=workflow, adapter_output={"done": 1}
    )

    count = await ExecutionWorker.process_queued(batch_size=10)

    assert count == 1
    assert session.committed is True


async def test_process_queued_fails_when_adapter_raises(monkeypatch) -> None:
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    session = _patch_worker(
        monkeypatch,
        queued=[_execution()],
        workflow=workflow,
        adapter_raises=RuntimeError("n8n down"),
    )

    count = await ExecutionWorker.process_queued(batch_size=10)

    assert count == 1
    assert session.committed is True


async def test_process_queued_fails_unavailable_workflow(monkeypatch) -> None:
    session = _patch_worker(monkeypatch, queued=[_execution()], workflow=None)

    count = await ExecutionWorker.process_queued(batch_size=10)

    assert count == 1
    assert session.committed is True


async def test_timeout_stuck_marks_timed_out(monkeypatch) -> None:
    session = _patch_worker(
        monkeypatch, stuck=[_execution(status=ExecutionStatus.RUNNING)]
    )

    count = await ExecutionWorker.timeout_stuck()

    assert count == 1
    assert session.committed is True


async def test_sweep_runs_all_phases(monkeypatch) -> None:
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    _patch_worker(
        monkeypatch,
        queued=[_execution()],
        due=[_execution(status=ExecutionStatus.RETRYING)],
        stuck=[_execution(status=ExecutionStatus.RUNNING)],
        workflow=workflow,
    )

    stats = await ExecutionWorker.sweep()

    assert stats == {"retried": 1, "processed": 1, "timed_out": 1}
