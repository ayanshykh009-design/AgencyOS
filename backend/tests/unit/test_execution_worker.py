"""Unit tests: ExecutionWorker sweep logic with a fake session + adapters."""
from __future__ import annotations

import itertools
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import ExecutionEventType, ExecutionStatus, WorkflowStatus
from app.workers.execution_worker import ExecutionWorker

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000601")


class FakeSession:
    def add(self, obj: object) -> None:
        pass

    async def execute(self, *args: object, **kwargs: object) -> object:
        return None

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
    orgs: list | None = None,
    workflow: MagicMock | None = None,
    adapter_output: dict | None = None,
    adapter_raises: Exception | None = None,
) -> FakeSession:
    session = FakeSession()
    session.committed = False

    if workflow is not None:
        workflow.id = WORKFLOW_ID

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
                "get_many": lambda self, ids: AsyncMock(
                    return_value=[workflow] if workflow is not None else []
                )(),
            },
        ),
    )

    service_get_queued_orgs = AsyncMock(return_value=orgs or [ORG_ID])
    service_get_queued_for_org = AsyncMock(return_value=queued or [])
    service_get_queued_for_retry = AsyncMock(return_value=due or [])
    service_get_stuck_running = AsyncMock(return_value=stuck or [])
    service_retry = AsyncMock()
    service_start = AsyncMock(return_value=_execution(status=ExecutionStatus.RUNNING))
    service_complete = AsyncMock()
    service_fail = AsyncMock()
    service_fail_queued = AsyncMock()
    service_timeout = AsyncMock()
    service_record_event = AsyncMock()
    service_record_events = AsyncMock()

    class FakeExecutionService:
        def __init__(self, s) -> None:
            pass

        get_queued_orgs = service_get_queued_orgs
        get_queued_for_org = service_get_queued_for_org
        get_queued_for_retry = service_get_queued_for_retry
        get_stuck_running = service_get_stuck_running
        retry = service_retry
        start = service_start
        complete = service_complete
        fail = service_fail
        fail_queued = service_fail_queued
        timeout = service_timeout
        record_event = service_record_event
        record_events = service_record_events

    monkeypatch.setattr(
        "app.workers.execution_worker.WorkflowExecutionService", FakeExecutionService
    )

    automation_enabled = AsyncMock(return_value=True)

    class FakeAutomationControl:
        def __init__(self, s) -> None:
            pass

        is_enabled = automation_enabled

    monkeypatch.setattr(
        "app.workers.execution_worker.AutomationControlService", FakeAutomationControl
    )
    session.automation_enabled = automation_enabled
    session.service_get_queued_orgs = service_get_queued_orgs
    session.service_get_queued_for_org = service_get_queued_for_org
    session.service_start = service_start
    session.service_complete = service_complete
    session.service_fail = service_fail
    session.service_fail_queued = service_fail_queued
    session.service_timeout = service_timeout
    session.service_record_event = service_record_event
    session.service_record_events = service_record_events
    adapter = MagicMock(
        execute=AsyncMock(
            side_effect=(
                adapter_raises
                if adapter_raises
                else lambda *a, **k: adapter_output or {"ok": True}
            )
        )
    )
    session.adapter_event_sink = None

    def _get_adapter(mode, event_sink=None):
        session.adapter_event_sink = event_sink
        return adapter

    monkeypatch.setattr("app.workers.execution_worker.get_adapter", _get_adapter)
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
    session.service_complete.assert_awaited_once()
    assert session.adapter_event_sink is not None
    dispatched = [
        c
        for c in session.service_record_event.await_args_list
        if c.args[1] == ExecutionEventType.ADAPTER_DISPATCHED
    ]
    returned = [
        c
        for c in session.service_record_event.await_args_list
        if c.args[1] == ExecutionEventType.ADAPTER_RETURNED
    ]
    assert dispatched
    assert returned


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


async def test_process_queued_batch_fetches_workflows(monkeypatch) -> None:
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    session = _patch_worker(
        monkeypatch, queued=[_execution()], workflow=workflow, adapter_output={"ok": True}
    )
    session.workflow_get_many = AsyncMock(return_value=[workflow])
    session.workflow_get_many_calls = 0

    class FakeWorkflowRepo:
        def __init__(self, s) -> None:
            pass

        def get_many(self, ids):
            session.workflow_get_many_calls += 1
            session.workflow_ids = ids
            return session.workflow_get_many(ids)

    monkeypatch.setattr("app.workers.execution_worker.WorkflowRepository", FakeWorkflowRepo)

    await ExecutionWorker.process_queued(batch_size=10)

    assert session.workflow_get_many_calls == 1
    assert session.workflow_ids == [WORKFLOW_ID]


async def test_process_queued_fair_drain_visits_each_org(monkeypatch) -> None:
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    session = _patch_worker(
        monkeypatch,
        queued=[_execution()],
        orgs=[ORG_ID, uuid.UUID("00000000-0000-0000-0000-000000000002")],
        workflow=workflow,
        adapter_output={"ok": True},
    )

    count = await ExecutionWorker.process_queued(batch_size=10)

    assert count == 2
    assert session.service_get_queued_for_org.await_count == 2
    assert session.service_complete.await_count == 2


async def test_process_queued_fails_unavailable_workflow(monkeypatch) -> None:
    session = _patch_worker(monkeypatch, queued=[_execution()], workflow=None)

    count = await ExecutionWorker.process_queued(batch_size=10)

    assert count == 1
    assert session.committed is True


async def test_process_queued_fails_unavailable_workflow_without_dispatch(
    monkeypatch,
) -> None:
    session = _patch_worker(monkeypatch, queued=[_execution()], workflow=None)

    await ExecutionWorker.process_queued(batch_size=10)

    _, kwargs = session.service_fail_queued.await_args
    assert kwargs["error"]["error"] == "workflow_unavailable"
    session.adapter.execute.assert_not_awaited()


async def test_process_queued_marks_timed_out_on_hard_timeout(monkeypatch) -> None:
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    session = _patch_worker(
        monkeypatch,
        queued=[_execution()],
        workflow=workflow,
        adapter_raises=TimeoutError("slow adapter"),
    )

    count = await ExecutionWorker.process_queued(batch_size=10)

    assert count == 1
    assert session.committed is True
    assert session.service_timeout.await_count == 1
    session.adapter.execute.assert_awaited_once()
    timeout_guard = [
        c
        for c in session.service_record_event.await_args_list
        if c.args[1] == ExecutionEventType.TIMEOUT_GUARD
    ]
    assert timeout_guard


async def test_process_queued_forwards_adapter_events_to_timeline(
    monkeypatch,
) -> None:
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="builtin", config={})
    session = _patch_worker(
        monkeypatch, queued=[_execution()], workflow=workflow, adapter_output={"ok": True}
    )

    count = await ExecutionWorker.process_queued(batch_size=10)

    assert count == 1
    assert session.adapter_event_sink is not None
    events = [(ExecutionEventType.STEP_STARTED, {"step_index": 0, "step_id": "s1"})]
    await session.adapter_event_sink(events)
    session.service_record_events.assert_awaited_once()
    assert session.service_record_events.await_args.args[1] == events


async def test_process_queued_skips_concurrent_state_change(monkeypatch) -> None:
    from app.core.errors import AppError

    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    session = _patch_worker(monkeypatch, queued=[_execution()], workflow=workflow)
    session.service_start.side_effect = AppError(
        code="execution.invalid_state",
        message="claimed concurrently",
        status_code=409,
    )

    count = await ExecutionWorker.process_queued(batch_size=10)

    assert count == 0
    assert session.committed is True
    session.adapter.execute.assert_not_awaited()


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


async def test_sweep_skips_queue_phases_when_automation_paused(monkeypatch) -> None:
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    session = _patch_worker(
        monkeypatch,
        queued=[_execution()],
        due=[_execution(status=ExecutionStatus.RETRYING)],
        stuck=[_execution(status=ExecutionStatus.RUNNING)],
        workflow=workflow,
    )
    session.automation_enabled.return_value = False

    stats = await ExecutionWorker.sweep()

    assert stats == {"retried": 0, "processed": 0, "timed_out": 1}
    session.service_get_queued_for_org.assert_not_awaited()
    session.service_start.assert_not_awaited()
    session.service_timeout.assert_awaited_once()


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


def _patch_heartbeat(monkeypatch) -> MagicMock:
    heartbeat = AsyncMock()
    session = MagicMock()
    session.commit = AsyncMock()

    class _FakeSessionCM:
        async def __aenter__(self) -> object:
            return session

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    monkeypatch.setattr(
        "app.workers.execution_worker.async_session_factory", lambda: _FakeSessionCM()
    )

    class _FakeHealthService:
        def __init__(self, s: object) -> None:
            pass

    _FakeHealthService.heartbeat = heartbeat

    monkeypatch.setattr(
        "app.workers.execution_worker.WorkerHealthService", _FakeHealthService
    )
    return heartbeat


async def test_heartbeat_writes_loop_ok(monkeypatch) -> None:
    from app.workers.execution_worker import _INSTANCE_ID, _WORKER_TYPE

    heartbeat = _patch_heartbeat(monkeypatch)

    await ExecutionWorker.heartbeat(loop_ok=True, last_error=None)

    _, kwargs = heartbeat.await_args
    assert kwargs["worker_type"] == _WORKER_TYPE
    assert kwargs["instance_id"] == _INSTANCE_ID
    assert kwargs["loop_ok"] is True
    assert kwargs["last_error"] is None
    assert "execution_drained_total" in kwargs["counters"]


async def test_heartbeat_reports_failure(monkeypatch) -> None:
    heartbeat = _patch_heartbeat(monkeypatch)

    await ExecutionWorker.heartbeat(loop_ok=False, last_error="sweep failed")

    _, kwargs = heartbeat.await_args
    assert kwargs["loop_ok"] is False
    assert kwargs["last_error"] == "sweep failed"


async def test_heartbeat_failure_is_best_effort(monkeypatch) -> None:
    heartbeat = _patch_heartbeat(monkeypatch)
    heartbeat.side_effect = RuntimeError("db down")

    # A heartbeat failure must never raise out of the worker loop.
    await ExecutionWorker.heartbeat(loop_ok=True)


async def test_process_queued_records_phase_telemetry(monkeypatch) -> None:
    from app.core.metrics import read_histogram, reset

    reset()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, execution_mode="n8n", config={})
    _patch_worker(
        monkeypatch, queued=[_execution()], workflow=workflow, adapter_output={"ok": True}
    )

    await ExecutionWorker.process_queued(batch_size=10)

    snapshot = read_histogram("execution_worker_phase_seconds")
    assert snapshot.count == 1
    assert snapshot.sum >= 0
