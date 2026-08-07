"""Unit tests: schedule dispatcher business rules (app.services.schedule_dispatcher)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from app.core.errors import AppError
from app.core.metrics import read_counter, reset
from app.models.enums import WorkflowTriggerType
from app.services.schedule_dispatcher import ScheduleDispatcher

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
TRIGGER_ID = uuid.UUID("00000000-0000-0000-0000-000000000701")
EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000601")

NOW = datetime(2026, 8, 4, 10, 30, tzinfo=UTC)
PREV_FIRE = datetime(2026, 8, 4, 10, 30, tzinfo=UTC)


class FakeSavepoint:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeSavepoint:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self._session.savepoint_rolled_back = True


class FakeSession:
    async def rollback(self) -> None:
        self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    def begin_nested(self) -> FakeSavepoint:
        self.savepoint_rolled_back = False
        return FakeSavepoint(self)


def _trigger(**overrides: object) -> MagicMock:
    trigger = MagicMock()
    trigger.id = TRIGGER_ID
    trigger.organization_id = ORG_ID
    trigger.workflow_id = WORKFLOW_ID
    trigger.trigger_type = WorkflowTriggerType.SCHEDULE
    trigger.schedule_cron = "*/5 * * * *"
    trigger.config = {"channel": "email"}
    trigger.last_fired_at = None
    for key, value in overrides.items():
        setattr(trigger, key, value)
    return trigger


def _dispatcher(
    *,
    triggers: list | None = None,
    reservation_wins: bool = True,
    queue_raises: AppError | None = None,
) -> tuple[ScheduleDispatcher, FakeSession]:
    session = FakeSession()
    dispatcher = ScheduleDispatcher(session)  # type: ignore[arg-type]
    trigger_repo = MagicMock()
    trigger_repo.list_enabled_schedules = AsyncMock(return_value=triggers or [])
    trigger_repo.reserve_last_fired = AsyncMock(return_value=reservation_wins)
    dispatcher._trigger_repo = trigger_repo

    execution_service = MagicMock()
    execution = MagicMock()
    execution.id = EXECUTION_ID
    queue = AsyncMock(
        side_effect=queue_raises if queue_raises else lambda *args, **kwargs: execution
    )
    execution_service.queue = queue
    dispatcher._execution_service = execution_service

    automation_control = MagicMock()
    automation_control.is_enabled = AsyncMock(return_value=True)
    dispatcher._automation_control = automation_control
    return dispatcher, session


async def test_dispatch_is_noop_when_automation_paused() -> None:
    dispatcher, session = _dispatcher(triggers=[_trigger()])
    dispatcher._automation_control.is_enabled = AsyncMock(return_value=False)

    stats = await dispatcher.dispatch_due(now=NOW)

    assert stats == {"scanned": 0, "queued": 0, "failed": 0, "skipped": 0, "conflicts": 0}
    dispatcher._trigger_repo.list_enabled_schedules.assert_not_awaited()
    dispatcher._trigger_repo.reserve_last_fired.assert_not_awaited()
    dispatcher._execution_service.queue.assert_not_called()
    assert not hasattr(session, "committed")


async def test_dispatch_proceeds_when_automation_enabled() -> None:
    dispatcher, session = _dispatcher(triggers=[_trigger()])
    dispatcher._automation_control.is_enabled = AsyncMock(return_value=True)

    stats = await dispatcher.dispatch_due(now=NOW)

    assert stats["queued"] == 1
    dispatcher._trigger_repo.list_enabled_schedules.assert_awaited_once()
    assert session.savepoint_rolled_back is False


async def test_empty_scan_returns_zero_stats() -> None:
    dispatcher, _ = _dispatcher()
    stats = await dispatcher.dispatch_due(now=NOW)
    assert stats == {"scanned": 0, "queued": 0, "failed": 0, "skipped": 0, "conflicts": 0}


async def test_due_trigger_is_reserved_and_queued() -> None:
    dispatcher, session = _dispatcher(triggers=[_trigger()])
    stats = await dispatcher.dispatch_due(now=NOW)

    assert stats == {"scanned": 1, "queued": 1, "failed": 0, "skipped": 0, "conflicts": 0}
    dispatcher._trigger_repo.reserve_last_fired.assert_awaited_once_with(TRIGGER_ID, PREV_FIRE, NOW)
    payload = dispatcher._execution_service.queue.await_args.args[0]
    assert payload.organization_id == ORG_ID
    assert payload.workflow_id == WORKFLOW_ID
    assert payload.trigger_id == TRIGGER_ID
    assert payload.input["trigger_config"] == {"channel": "email"}
    assert payload.input["scheduled_at"] == "2026-08-04T10:30:00+00:00"


async def test_already_fired_tick_is_skipped() -> None:
    dispatcher, _ = _dispatcher(triggers=[_trigger(last_fired_at=PREV_FIRE)])
    stats = await dispatcher.dispatch_due(now=NOW)

    assert stats["skipped"] == 1
    assert stats["queued"] == 0
    dispatcher._trigger_repo.reserve_last_fired.assert_not_called()


async def test_older_than_previous_fire_still_dispatches() -> None:
    old = datetime(2026, 8, 4, 10, 25, tzinfo=UTC)
    dispatcher, _ = _dispatcher(triggers=[_trigger(last_fired_at=old)])
    stats = await dispatcher.dispatch_due(now=NOW)
    assert stats["queued"] == 1


async def test_lost_reservation_conflict_does_not_queue() -> None:
    dispatcher, _ = _dispatcher(triggers=[_trigger()], reservation_wins=False)
    stats = await dispatcher.dispatch_due(now=NOW)

    assert stats["conflicts"] == 1
    assert stats["queued"] == 0
    dispatcher._execution_service.queue.assert_not_called()


async def test_queue_failure_rolls_back_reservation() -> None:
    dispatcher, session = _dispatcher(
        triggers=[_trigger()],
        queue_raises=AppError(code="workflow.not_active", message="not active", status_code=400),
    )
    stats = await dispatcher.dispatch_due(now=NOW)

    assert stats["failed"] == 1
    assert stats["queued"] == 0
    assert session.savepoint_rolled_back is True
    assert not hasattr(session, "rolled_back")


async def test_partial_batch_failure_preserves_earlier_queue() -> None:
    """A queue failure for one trigger must not discard earlier dispatches."""
    session = FakeSession()
    dispatcher = ScheduleDispatcher(session)  # type: ignore[arg-type]

    trigger_repo = MagicMock()
    trigger_repo.list_enabled_schedules = AsyncMock(
        return_value=[
            _trigger(),
            _trigger(id=uuid.UUID("00000000-0000-0000-0000-000000000703")),
        ]
    )
    trigger_repo.reserve_last_fired = AsyncMock(return_value=True)
    dispatcher._trigger_repo = trigger_repo

    automation_control = MagicMock()
    automation_control.is_enabled = AsyncMock(return_value=True)
    dispatcher._automation_control = automation_control

    execution = MagicMock()
    execution.id = EXECUTION_ID
    calls = {"n": 0}

    async def queue(*args: object, **kwargs: object) -> MagicMock:
        calls["n"] += 1
        if calls["n"] == 2:
            raise AppError(code="workflow.not_active", message="not active", status_code=400)
        return execution

    execution_service = MagicMock()
    execution_service.queue = AsyncMock(side_effect=queue)
    dispatcher._execution_service = execution_service

    stats = await dispatcher.dispatch_due(now=NOW)

    assert stats == {"scanned": 2, "queued": 1, "failed": 1, "skipped": 0, "conflicts": 0}
    assert session.savepoint_rolled_back is True


async def test_invalid_cron_is_skipped() -> None:
    dispatcher, _ = _dispatcher(triggers=[_trigger(schedule_cron="not a cron")])
    stats = await dispatcher.dispatch_due(now=NOW)
    assert stats["skipped"] == 1
    dispatcher._trigger_repo.reserve_last_fired.assert_not_called()


async def test_never_firing_cron_is_skipped() -> None:
    dispatcher, _ = _dispatcher(triggers=[_trigger(schedule_cron="0 0 31 2 *")])
    stats = await dispatcher.dispatch_due(now=NOW)
    assert stats["skipped"] == 1


async def test_metrics_recorded_per_outcome() -> None:
    reset()
    triggers = [
        _trigger(),  # queued
        _trigger(id=uuid.UUID("00000000-0000-0000-0000-000000000702"), last_fired_at=PREV_FIRE),
    ]
    dispatcher, _ = _dispatcher(triggers=triggers)
    await dispatcher.dispatch_due(now=NOW)

    assert read_counter("schedule_dispatch_success") == 1
    assert read_counter("queue_success") == 1
    assert read_counter("schedule_dispatch_skip") == 1
    assert read_counter("schedule_dispatch_failure") == 0
    assert read_counter("reservation_conflict") == 0


async def test_dispatch_failure_increments_failure_metrics() -> None:
    reset()
    dispatcher, _ = _dispatcher(
        triggers=[_trigger()],
        queue_raises=AppError(code="workflow.not_active", message="not active", status_code=400),
    )
    await dispatcher.dispatch_due(now=NOW)

    assert read_counter("schedule_dispatch_failure") == 1
    assert read_counter("queue_failure") == 1


async def test_batch_limit_passed_to_repository() -> None:
    dispatcher, _ = _dispatcher(triggers=[])
    await dispatcher.dispatch_due(now=NOW, limit=7)
    dispatcher._trigger_repo.list_enabled_schedules.assert_awaited_once_with(7)
