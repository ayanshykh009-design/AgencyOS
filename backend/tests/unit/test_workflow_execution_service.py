"""Service-layer unit tests: workflow execution state machine and retries."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.errors import AppError
from app.models.enums import ExecutionStatus, WorkflowStatus
from app.schemas.workflow_execution import WorkflowExecutionCreate
from app.services.workflow_execution_service import WorkflowExecutionService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000201")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000601")


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def add(self, obj: object) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def _service() -> WorkflowExecutionService:
    service = WorkflowExecutionService(FakeSession())
    service._repo = MagicMock()
    service._repo.flush = AsyncMock()
    service._repo.refresh = AsyncMock()
    service._repo.add = MagicMock()
    service._repo.count_pending = AsyncMock(return_value=0)
    service._workflow_repo = MagicMock()
    service._events = MagicMock()
    service._events.record = AsyncMock()
    service._events.record_many = AsyncMock()
    service._logs = MagicMock()
    service._logs.add = MagicMock()
    service._automation_control = MagicMock()
    service._automation_control.block_queue_if_paused = AsyncMock()
    service._automation_control.block_execution_if_paused = AsyncMock()
    return service


def _execution(**overrides: object) -> MagicMock:
    execution = MagicMock()
    execution.id = EXECUTION_ID
    execution.organization_id = ORG_ID
    execution.status = ExecutionStatus.QUEUED
    execution.attempts = 0
    execution.max_attempts = 3
    execution.retry_delay_seconds = 60
    execution.retry_backoff = "exponential"
    execution.next_retry_at = None
    execution.cancel_requested_at = None
    execution.cancelled_by_user_id = None
    for key, value in overrides.items():
        setattr(execution, key, value)
    return execution


def _queue() -> WorkflowExecutionCreate:
    return WorkflowExecutionCreate(
        organization_id=ORG_ID,
        workflow_id=WORKFLOW_ID,
        input={"lead_id": "x"},
        max_attempts=3,
        retry_delay_seconds=60,
        retry_backoff="exponential",
        trace_id=uuid.uuid4(),
    )


async def test_queue_blocks_when_automation_paused() -> None:
    service = _service()
    service._automation_control.block_queue_if_paused = AsyncMock(
        side_effect=AppError(
            code="automation.paused.queue_blocked",
            message="Automation is currently paused. New executions cannot be queued.",
            status_code=409,
        )
    )

    with pytest.raises(AppError) as exc_info:
        await service.queue(_queue())

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "automation.paused.queue_blocked"
    service._workflow_repo.get.assert_not_called()
    service._repo.add.assert_not_called()


async def test_retry_blocks_when_automation_paused() -> None:
    service = _service()
    service._automation_control.block_execution_if_paused = AsyncMock(
        side_effect=AppError(
            code="automation.paused",
            message="Automation is currently paused. Operations are blocked until resumed.",
            status_code=409,
        )
    )

    with pytest.raises(AppError) as exc_info:
        await service.retry(ORG_ID, EXECUTION_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "automation.paused"
    service._repo.get_or_404.assert_not_called()
    service._repo.mark_requeued.assert_not_called()


async def test_queue_requires_active_workflow() -> None:
    service = _service()
    service._workflow_repo.get = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.queue(_queue(), requested_by_user_id=USER_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "workflow.not_found"


async def test_queue_rejects_inactive_workflow() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.DRAFT)
    service._workflow_repo.get = AsyncMock(return_value=workflow)

    with pytest.raises(AppError) as exc_info:
        await service.queue(_queue())

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "workflow.not_active"


async def test_queue_creates_queued_execution() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE)
    service._workflow_repo.get = AsyncMock(return_value=workflow)
    created: list[object] = []
    service._repo.add.side_effect = lambda instance: created.append(instance)

    await service.queue(_queue(), requested_by_user_id=USER_ID)

    instance = created[0]
    assert instance.status == ExecutionStatus.QUEUED
    assert instance.organization_id == ORG_ID
    assert instance.workflow_id == WORKFLOW_ID
    assert instance.requested_by_user_id == USER_ID


async def test_queue_commits_transaction() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE)
    service._workflow_repo.get = AsyncMock(return_value=workflow)
    service._repo.add.side_effect = lambda instance: None

    await service.queue(_queue(), requested_by_user_id=USER_ID)

    assert service._session.commits == 1


async def test_queue_refuses_when_pending_cap_exceeded() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE)
    service._workflow_repo.get = AsyncMock(return_value=workflow)
    service._repo.count_pending = AsyncMock(
        return_value=settings.EXECUTION_MAX_PENDING_PER_ORG
    )

    with pytest.raises(AppError) as exc_info:
        await service.queue(_queue())

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "execution.pending_cap_exceeded"
    service._repo.add.assert_not_called()


async def test_queue_bypasses_pending_cap_with_manage() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE)
    service._workflow_repo.get = AsyncMock(return_value=workflow)
    service._repo.count_pending = AsyncMock(
        return_value=settings.EXECUTION_MAX_PENDING_PER_ORG
    )

    await service.queue(_queue(), bypass_pending_cap=True)

    service._repo.add.assert_called_once()


async def test_queue_increments_queued_counter() -> None:
    from app.core.metrics import read_counter, reset

    reset()
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE)
    service._workflow_repo.get = AsyncMock(return_value=workflow)
    service._repo.add.side_effect = lambda instance: None

    await service.queue(_queue())

    assert read_counter("execution_queued_total") == 1


async def test_queue_maps_integrity_error() -> None:
    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE)
    service._workflow_repo.get = AsyncMock(return_value=workflow)
    service._repo.flush = AsyncMock(side_effect=IntegrityError("", {}, Exception()))

    with pytest.raises(AppError) as exc_info:
        await service.queue(_queue())

    assert exc_info.value.code == "execution.create_failed"


async def test_start_requires_queued_state() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.SUCCEEDED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    with pytest.raises(AppError) as exc_info:
        await service.start(ORG_ID, EXECUTION_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "execution.invalid_state"


async def test_start_transitions_to_running_and_bumps_attempts() -> None:
    service = _service()
    execution = _execution()
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(
        status=ExecutionStatus.RUNNING,
        attempts=1,
        started_at=datetime.now(UTC),
    )
    service._repo.mark_started = AsyncMock(return_value=updated)

    result = await service.start(ORG_ID, EXECUTION_ID)

    service._repo.mark_started.assert_awaited_once_with(ORG_ID, EXECUTION_ID)
    assert result.status == ExecutionStatus.RUNNING
    assert result.attempts == 1
    assert result.started_at is not None


async def test_start_rejects_concurrent_claim() -> None:
    service = _service()
    execution = _execution()
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    service._repo.mark_started = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.start(ORG_ID, EXECUTION_ID)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "execution.invalid_state"


async def test_complete_requires_running() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.QUEUED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    with pytest.raises(AppError) as exc_info:
        await service.complete(ORG_ID, EXECUTION_ID, output={"ok": True})

    assert exc_info.value.status_code == 409


async def test_complete_sets_succeeded() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(
        status=ExecutionStatus.SUCCEEDED,
        output={"ok": True},
        finished_at=datetime.now(UTC),
    )
    service._repo.mark_succeeded = AsyncMock(return_value=updated)

    await service.complete(ORG_ID, EXECUTION_ID, output={"ok": True})

    service._repo.mark_succeeded.assert_awaited_once()
    assert updated.status == ExecutionStatus.SUCCEEDED
    assert updated.output == {"ok": True}
    assert updated.finished_at is not None


async def test_complete_honors_cancel_flag() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    service._repo.mark_succeeded = AsyncMock(return_value=None)
    cancelled = _execution(status=ExecutionStatus.CANCELLED)
    service._repo.mark_cancelled_after_run = AsyncMock(return_value=cancelled)

    result = await service.complete(ORG_ID, EXECUTION_ID, output={"ok": True})

    assert result.status == ExecutionStatus.CANCELLED
    service._repo.mark_cancelled_after_run.assert_awaited_once()


async def test_complete_concurrent_state_raises() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    service._repo.mark_succeeded = AsyncMock(return_value=None)
    service._repo.mark_cancelled_after_run = AsyncMock(return_value=None)

    with pytest.raises(AppError) as exc_info:
        await service.complete(ORG_ID, EXECUTION_ID, output={"ok": True})

    assert exc_info.value.status_code == 409


async def test_fail_schedules_retry_when_attempts_remain() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, attempts=1)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(
        status=ExecutionStatus.RETRYING,
        attempts=1,
        next_retry_at=datetime.now(UTC),
        error={"error": "boom"},
    )
    service._repo.mark_failed = AsyncMock(return_value=updated)

    await service.fail(ORG_ID, EXECUTION_ID, error={"error": "boom"}, schedule_retry=True)

    service._repo.mark_failed.assert_awaited_once()
    _, kwargs = service._repo.mark_failed.await_args
    assert kwargs["to_status"] == ExecutionStatus.RETRYING
    assert kwargs["next_retry_at"] is not None
    assert kwargs["error"] == {"error": "boom"}
    assert updated.status == ExecutionStatus.RETRYING


async def test_fail_marks_failed_when_attempts_exhausted() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, attempts=3)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.FAILED, attempts=3, next_retry_at=None)
    service._repo.mark_failed = AsyncMock(return_value=updated)

    await service.fail(ORG_ID, EXECUTION_ID, error={"error": "boom"})

    service._repo.mark_failed.assert_awaited_once()
    _, kwargs = service._repo.mark_failed.await_args
    assert kwargs["to_status"] == ExecutionStatus.FAILED
    assert kwargs["next_retry_at"] is None
    assert updated.status == ExecutionStatus.FAILED


async def test_fail_respects_schedule_retry_flag() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, attempts=1)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.FAILED, attempts=1, next_retry_at=None)
    service._repo.mark_failed = AsyncMock(return_value=updated)

    await service.fail(ORG_ID, EXECUTION_ID, error={"error": "boom"}, schedule_retry=False)

    service._repo.mark_failed.assert_awaited_once()
    _, kwargs = service._repo.mark_failed.await_args
    assert kwargs["to_status"] == ExecutionStatus.FAILED
    assert kwargs["next_retry_at"] is None


async def test_fail_honors_cancel_flag() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, cancel_requested_at=datetime.now(UTC))
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    cancelled = _execution(status=ExecutionStatus.CANCELLED)
    service._repo.mark_cancelled_after_run = AsyncMock(return_value=cancelled)

    result = await service.fail(ORG_ID, EXECUTION_ID, error={"error": "boom"})

    assert result.status == ExecutionStatus.CANCELLED
    service._repo.mark_cancelled_after_run.assert_awaited_once()
    service._repo.mark_failed.assert_not_called()


async def test_fail_queued_marks_failed() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.QUEUED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.FAILED, error={"error": "gone"})
    service._repo.mark_failed_if_queued = AsyncMock(return_value=updated)

    result = await service.fail_queued(ORG_ID, EXECUTION_ID, error={"error": "gone"})

    service._repo.mark_failed_if_queued.assert_awaited_once()
    assert result.status == ExecutionStatus.FAILED


async def test_fail_queued_rejects_running() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    with pytest.raises(AppError) as exc_info:
        await service.fail_queued(ORG_ID, EXECUTION_ID, error={"error": "gone"})

    assert exc_info.value.status_code == 409


async def test_payload_too_large_rejects_output() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    with pytest.raises(AppError) as exc_info:
        await service.complete(
            ORG_ID, EXECUTION_ID, output={"blob": "x" * 600000}
        )

    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "execution.payload_too_large"


def test_retry_delay_exponential_doubles() -> None:
    execution = _execution(attempts=2, retry_backoff="exponential", retry_delay_seconds=60)
    assert WorkflowExecutionService._retry_delay_seconds(execution) == 120


def test_retry_delay_constant() -> None:
    execution = _execution(attempts=5, retry_backoff="constant", retry_delay_seconds=30)
    assert WorkflowExecutionService._retry_delay_seconds(execution) == 30


async def test_manual_retry_requeues_failed() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.FAILED, next_retry_at=datetime.now(UTC))
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.QUEUED, next_retry_at=None)
    service._repo.mark_requeued = AsyncMock(return_value=updated)

    await service.retry(ORG_ID, EXECUTION_ID)

    service._repo.mark_requeued.assert_awaited_once_with(ORG_ID, EXECUTION_ID)
    assert updated.status == ExecutionStatus.QUEUED
    assert updated.next_retry_at is None


async def test_manual_retry_rejects_succeeded() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.SUCCEEDED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    with pytest.raises(AppError) as exc_info:
        await service.retry(ORG_ID, EXECUTION_ID)

    assert exc_info.value.status_code == 409


async def test_cancel_pending_states_cancel_immediately() -> None:
    for status in (ExecutionStatus.QUEUED, ExecutionStatus.RETRYING):
        service = _service()
        execution = _execution(status=status)
        service._repo.get_or_404 = AsyncMock(return_value=execution)
        updated = _execution(
            status=ExecutionStatus.CANCELLED,
            finished_at=datetime.now(UTC),
        )
        service._repo.mark_cancelled_if_pending = AsyncMock(return_value=updated)

        result = await service.cancel(ORG_ID, EXECUTION_ID)

        service._repo.mark_cancelled_if_pending.assert_awaited_once()
        assert result.status == ExecutionStatus.CANCELLED
        assert result.finished_at is not None


async def test_cancel_running_flags_cancel_requested() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(
        status=ExecutionStatus.RUNNING,
        cancel_requested_at=datetime.now(UTC),
    )
    service._repo.mark_cancel_requested = AsyncMock(return_value=updated)

    result = await service.cancel(ORG_ID, EXECUTION_ID)

    service._repo.mark_cancel_requested.assert_awaited_once()
    assert result.status == ExecutionStatus.RUNNING
    assert result.cancel_requested_at is not None


async def test_cancel_already_cancelled_is_noop() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.CANCELLED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    result = await service.cancel(ORG_ID, EXECUTION_ID)

    assert result is execution
    service._repo.mark_cancelled_if_pending.assert_not_called()
    service._repo.mark_cancel_requested.assert_not_called()


async def test_cancel_rejects_terminal() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.SUCCEEDED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    with pytest.raises(AppError) as exc_info:
        await service.cancel(ORG_ID, EXECUTION_ID)

    assert exc_info.value.status_code == 409


async def test_timeout_marks_timed_out() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(
        status=ExecutionStatus.TIMED_OUT,
        error={"error": "execution timed out"},
        finished_at=datetime.now(UTC),
    )
    service._repo.mark_timed_out = AsyncMock(return_value=updated)

    await service.timeout(ORG_ID, EXECUTION_ID)

    service._repo.mark_timed_out.assert_awaited_once()
    _, kwargs = service._repo.mark_timed_out.await_args
    assert kwargs["error"] == {"error": "execution timed out"}
    assert updated.status == ExecutionStatus.TIMED_OUT


async def test_timeout_honors_cancel_flag() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    service._repo.mark_timed_out = AsyncMock(return_value=None)
    cancelled = _execution(status=ExecutionStatus.CANCELLED)
    service._repo.mark_cancelled_after_run = AsyncMock(return_value=cancelled)

    result = await service.timeout(ORG_ID, EXECUTION_ID)

    assert result.status == ExecutionStatus.CANCELLED
    service._repo.mark_cancelled_after_run.assert_awaited_once()


async def test_worker_helpers_delegate() -> None:
    service = _service()
    queued = [_execution()]
    due = [_execution(status=ExecutionStatus.RETRYING)]
    stuck = [_execution(status=ExecutionStatus.RUNNING)]
    service._repo.get_queued = AsyncMock(return_value=queued)
    service._repo.get_queued_for_retry = AsyncMock(return_value=due)
    service._repo.get_stuck_running = AsyncMock(return_value=stuck)

    assert await service.get_queued(5) == queued
    assert await service.get_queued_for_retry() == due
    assert await service.get_stuck_running() == stuck

    before = datetime.now(UTC) - timedelta(seconds=300)
    await service.get_queued_for_retry(before)
    service._repo.get_queued_for_retry.assert_awaited_with(before)


def _timeline_types(service: WorkflowExecutionService) -> list[object]:
    return [c.kwargs["event_type"] for c in service._events.record.await_args_list]


def _audit_events(service: WorkflowExecutionService) -> list[object]:
    return [c.args[0].event_type for c in service._logs.add.call_args_list]


async def test_queue_writes_queued_timeline_and_audit() -> None:
    from app.models.enums import ActivityEventType, ExecutionEventType

    service = _service()
    workflow = MagicMock(status=WorkflowStatus.ACTIVE, name="Engage")
    service._workflow_repo.get = AsyncMock(return_value=workflow)
    service._repo.add.side_effect = lambda instance: None

    await service.queue(_queue(), requested_by_user_id=USER_ID)

    assert _timeline_types(service) == [ExecutionEventType.QUEUED]
    queued_call = service._events.record.await_args.kwargs
    assert queued_call["event_type"] == ExecutionEventType.QUEUED
    assert queued_call["metadata"]["actor"] == str(USER_ID)
    assert _audit_events(service) == [ActivityEventType.EXECUTION_QUEUED]


async def test_start_writes_started_timeline() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution()
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.RUNNING, attempts=1)
    service._repo.mark_started = AsyncMock(return_value=updated)

    await service.start(ORG_ID, EXECUTION_ID, actor_user_id=USER_ID)

    assert _timeline_types(service) == [ExecutionEventType.STARTED]
    metadata = service._events.record.await_args.kwargs["metadata"]
    assert metadata["actor"] == str(USER_ID)


async def test_complete_writes_succeeded_timeline_with_duration() -> None:
    from app.core.metrics import read_histogram, reset
    from app.models.enums import ExecutionEventType

    reset()
    service = _service()
    started_at = datetime.now(UTC) - timedelta(seconds=2)
    execution = _execution(status=ExecutionStatus.RUNNING, started_at=started_at)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(
        status=ExecutionStatus.SUCCEEDED,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    service._repo.mark_succeeded = AsyncMock(return_value=updated)

    await service.complete(ORG_ID, EXECUTION_ID, output={"ok": True})

    assert _timeline_types(service) == [ExecutionEventType.SUCCEEDED]
    metadata = service._events.record.await_args.kwargs["metadata"]
    assert metadata["duration_ms"] is not None
    assert metadata["duration_ms"] >= 1900
    snapshot = read_histogram("execution_duration_seconds")
    assert snapshot.count == 1
    assert snapshot.sum >= 1.9


async def test_complete_cancel_win_writes_cancelled_timeline() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    service._repo.mark_succeeded = AsyncMock(return_value=None)
    cancelled = _execution(status=ExecutionStatus.CANCELLED)
    service._repo.mark_cancelled_after_run = AsyncMock(return_value=cancelled)

    await service.complete(ORG_ID, EXECUTION_ID, output={"ok": True})

    assert _timeline_types(service) == [ExecutionEventType.CANCELLED]


async def test_fail_writes_retrying_timeline() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, attempts=1)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.RETRYING, attempts=1)
    service._repo.mark_failed = AsyncMock(return_value=updated)

    await service.fail(ORG_ID, EXECUTION_ID, error={"error": "boom"}, schedule_retry=True)

    assert _timeline_types(service) == [ExecutionEventType.RETRYING]
    metadata = service._events.record.await_args.kwargs["metadata"]
    assert metadata["error_code"] == "boom"


async def test_fail_exhausted_writes_failed_timeline() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, attempts=3)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.FAILED, attempts=3)
    service._repo.mark_failed = AsyncMock(return_value=updated)

    await service.fail(ORG_ID, EXECUTION_ID, error={"error": "boom"})

    assert _timeline_types(service) == [ExecutionEventType.FAILED]


async def test_fail_queued_writes_failed_timeline() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution(status=ExecutionStatus.QUEUED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.FAILED)
    service._repo.mark_failed_if_queued = AsyncMock(return_value=updated)

    await service.fail_queued(ORG_ID, EXECUTION_ID, error={"error": "gone"})

    assert _timeline_types(service) == [ExecutionEventType.FAILED]


async def test_retry_writes_retrying_timeline() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution(status=ExecutionStatus.FAILED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.QUEUED)
    service._repo.mark_requeued = AsyncMock(return_value=updated)

    await service.retry(ORG_ID, EXECUTION_ID, actor_user_id=USER_ID)

    assert _timeline_types(service) == [ExecutionEventType.RETRYING]
    metadata = service._events.record.await_args.kwargs["metadata"]
    assert metadata["actor"] == str(USER_ID)


async def test_cancel_writes_cancelled_timeline() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution(status=ExecutionStatus.QUEUED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(
        status=ExecutionStatus.CANCELLED,
        finished_at=datetime.now(UTC),
    )
    service._repo.mark_cancelled_if_pending = AsyncMock(return_value=updated)

    await service.cancel(
        ORG_ID, EXECUTION_ID, cancelled_by_user_id=USER_ID
    )

    assert _timeline_types(service) == [ExecutionEventType.CANCELLED]
    metadata = service._events.record.await_args.kwargs["metadata"]
    assert metadata["actor"] == str(USER_ID)


async def test_timeout_writes_timed_out_timeline() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING)
    service._repo.get_or_404 = AsyncMock(return_value=execution)
    updated = _execution(status=ExecutionStatus.TIMED_OUT)
    service._repo.mark_timed_out = AsyncMock(return_value=updated)

    await service.timeout(ORG_ID, EXECUTION_ID)

    assert _timeline_types(service) == [ExecutionEventType.TIMED_OUT]


async def test_record_events_delegates_to_batch_writer() -> None:
    from app.models.enums import ExecutionEventType

    service = _service()
    execution = _execution(attempts=2)
    events = [(ExecutionEventType.STEP_STARTED, {"step_index": 1})]

    await service.record_events(execution, events)

    service._events.record_many.assert_awaited_once()
    kwargs = service._events.record_many.await_args.kwargs
    assert kwargs["attempt"] == 2
    assert kwargs["events"] == events
