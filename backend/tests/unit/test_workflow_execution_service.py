"""Service-layer unit tests: workflow execution state machine and retries."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

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
    service._workflow_repo = MagicMock()
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

    result = await service.start(ORG_ID, EXECUTION_ID)

    assert execution.status == ExecutionStatus.RUNNING
    assert execution.attempts == 1
    assert execution.started_at is not None
    assert result is execution


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

    await service.complete(ORG_ID, EXECUTION_ID, output={"ok": True})

    assert execution.status == ExecutionStatus.SUCCEEDED
    assert execution.output == {"ok": True}
    assert execution.finished_at is not None


async def test_fail_schedules_retry_when_attempts_remain() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, attempts=1)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    await service.fail(ORG_ID, EXECUTION_ID, error={"error": "boom"}, schedule_retry=True)

    assert execution.status == ExecutionStatus.RETRYING
    assert execution.next_retry_at is not None
    assert execution.error == {"error": "boom"}


async def test_fail_marks_failed_when_attempts_exhausted() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, attempts=3)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    await service.fail(ORG_ID, EXECUTION_ID, error={"error": "boom"})

    assert execution.status == ExecutionStatus.FAILED
    assert execution.next_retry_at is None


async def test_fail_respects_schedule_retry_flag() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.RUNNING, attempts=1)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    await service.fail(
        ORG_ID, EXECUTION_ID, error={"error": "boom"}, schedule_retry=False
    )

    assert execution.status == ExecutionStatus.FAILED
    assert execution.next_retry_at is None


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

    await service.retry(ORG_ID, EXECUTION_ID)

    assert execution.status == ExecutionStatus.QUEUED
    assert execution.next_retry_at is None


async def test_manual_retry_rejects_succeeded() -> None:
    service = _service()
    execution = _execution(status=ExecutionStatus.SUCCEEDED)
    service._repo.get_or_404 = AsyncMock(return_value=execution)

    with pytest.raises(AppError) as exc_info:
        await service.retry(ORG_ID, EXECUTION_ID)

    assert exc_info.value.status_code == 409


async def test_cancel_allowed_states() -> None:
    for status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.RETRYING):
        service = _service()
        execution = _execution(status=status)
        service._repo.get_or_404 = AsyncMock(return_value=execution)

        await service.cancel(ORG_ID, EXECUTION_ID)

        assert execution.status == ExecutionStatus.CANCELLED
        assert execution.finished_at is not None


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

    await service.timeout(ORG_ID, EXECUTION_ID)

    assert execution.status == ExecutionStatus.TIMED_OUT
    assert execution.error == {"error": "execution timed out"}


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
