"""Unit tests: ExecutionWorker sweep logic with a fake session + adapters."""
from __future__ import annotations

import itertools
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    adapter = MagicMock(
        execute=AsyncMock(
            side_effect=(
                adapter_raises
                if adapter_raises
                else lambda *a, **k: adapter_output or {"ok": True}
            )
        )
    )
    monkeypatch.setattr("app.workers.execution_worker.get_adapter", lambda mode: adapter)
    session.adapter = adapter
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


async def test_process_queued_passes_workflow_definition_to_adapter(monkeypatch) -> None:
    definition = {"steps": [{"type": "set", "key": "a", "value": "1"}]}
    workflow = MagicMock(
        status=WorkflowStatus.ACTIVE,
        execution_mode="builtin",
        config={},
        definition=definition,
    )
    session = _patch_worker(
        monkeypatch, queued=[_execution()], workflow=workflow, adapter_output={"ok": True}
    )

    await ExecutionWorker.process_queued(batch_size=10)

    _, kwargs = session.adapter.execute.await_args
    assert kwargs["definition"] == definition
    assert kwargs["input_data"] == {"lead_id": "x"}


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


# --- Schedule dispatcher phase -------------------------------------------------


class _FakeDispatcher:
    def __init__(self, *, result: dict | None = None, raises: Exception | None = None):
        self.result = result or {"queued": 0}
        self.raises = raises
        self.calls = 0

    async def dispatch_due(self) -> dict:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.result


def _patch_schedule(
    monkeypatch,
    *,
    enabled: bool = True,
    dispatcher: _FakeDispatcher | None = None,
) -> _FakeDispatcher:
    monkeypatch.setattr(
        "app.workers.execution_worker.settings.SCHEDULE_DISPATCHER_ENABLED", enabled
    )

    class _FakeSessionCM:
        async def __aenter__(self) -> object:
            return MagicMock()

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    monkeypatch.setattr(
        "app.workers.execution_worker.async_session_factory", lambda: _FakeSessionCM()
    )
    fake = dispatcher or _FakeDispatcher()
    constructed: list[object] = []

    class _PatchedDispatcher:
        def __init__(self, s: object) -> None:
            constructed.append(s)

        async def dispatch_due(self) -> dict:
            return await fake.dispatch_due()

    monkeypatch.setattr("app.workers.execution_worker.ScheduleDispatcher", _PatchedDispatcher)
    fake.constructed = constructed  # type: ignore[attr-defined]
    return fake


async def test_schedule_tick_returns_queued_count(monkeypatch) -> None:
    fake = _patch_schedule(monkeypatch, dispatcher=_FakeDispatcher(result={"queued": 3}))

    queued = await ExecutionWorker.schedule_tick()

    assert queued == 3
    assert fake.calls == 1
    assert len(fake.constructed) == 1  # type: ignore[attr-defined]


async def test_schedule_tick_disabled_returns_zero(monkeypatch) -> None:
    fake = _patch_schedule(monkeypatch, enabled=False)

    assert await ExecutionWorker.schedule_tick() == 0
    assert fake.calls == 0
    assert fake.constructed == []  # type: ignore[attr-defined]


async def test_schedule_tick_propagates_dispatcher_errors(monkeypatch) -> None:
    _patch_schedule(monkeypatch, dispatcher=_FakeDispatcher(raises=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        await ExecutionWorker.schedule_tick()


async def test_run_loop_gates_schedule_to_its_own_cadence(monkeypatch) -> None:
    _patch_schedule(monkeypatch, dispatcher=_FakeDispatcher(result={"queued": 1}))
    monkeypatch.setattr(
        "app.workers.execution_worker.settings.EXECUTION_POLL_INTERVAL_SECONDS", 5
    )
    monkeypatch.setattr(
        "app.workers.execution_worker.settings.SCHEDULE_POLL_INTERVAL_SECONDS", 15
    )

    sweep = AsyncMock(return_value={"retried": 0, "processed": 0, "timed_out": 0})
    monkeypatch.setattr(ExecutionWorker, "sweep", sweep)
    schedule_tick = AsyncMock(return_value=1)
    monkeypatch.setattr(ExecutionWorker, "schedule_tick", schedule_tick)

    monotonic_values = itertools.cycle([0.0, 20.0])
    monkeypatch.setattr(
        "app.workers.execution_worker.time.monotonic", lambda: next(monotonic_values)
    )

    sleeps = 0

    async def _fake_sleep(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("app.workers.execution_worker.asyncio.sleep", _fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        await ExecutionWorker.run_loop()

    # Iteration 1: monotonic()=0 -> schedule not due. Iteration 2: 20 -> due once.
    assert schedule_tick.await_count == 1
    # Queue sweep still runs on every iteration, schedule never delays it.
    assert sweep.await_count == 2


async def test_run_loop_schedule_error_does_not_abort_loop(monkeypatch) -> None:
    _patch_schedule(monkeypatch, enabled=True)
    monkeypatch.setattr(
        "app.workers.execution_worker.settings.EXECUTION_POLL_INTERVAL_SECONDS", 5
    )
    monkeypatch.setattr(
        "app.workers.execution_worker.settings.SCHEDULE_POLL_INTERVAL_SECONDS", 1
    )

    sweep = AsyncMock(return_value={"retried": 0, "processed": 0, "timed_out": 0})
    monkeypatch.setattr(ExecutionWorker, "sweep", sweep)

    async def _boom_tick() -> int:
        raise RuntimeError("schedule boom")

    schedule_tick = AsyncMock(side_effect=_boom_tick)
    monkeypatch.setattr(ExecutionWorker, "schedule_tick", schedule_tick)

    monotonic_values = itertools.cycle([0.0, 5.0])
    monkeypatch.setattr(
        "app.workers.execution_worker.time.monotonic", lambda: next(monotonic_values)
    )

    sleeps = 0

    async def _fake_sleep(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("app.workers.execution_worker.asyncio.sleep", _fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        await ExecutionWorker.run_loop()

    # Schedule errors are contained: the sweep keeps running.
    assert schedule_tick.await_count == 1
    assert sweep.await_count == 2
