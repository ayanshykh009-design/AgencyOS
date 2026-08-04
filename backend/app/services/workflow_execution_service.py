"""WorkflowExecution service: queue management, execution, retry."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, ExecutionStatus, WorkflowStatus
from app.models.workflow_execution import WorkflowExecution
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.workflow import WorkflowRepository
from app.repositories.workflow_execution import WorkflowExecutionRepository
from app.schemas.workflow_execution import WorkflowExecutionCreate
from app.services.base import commit_with_retry, utcnow


class WorkflowExecutionService:
    """Owns execution lifecycle and queue operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = WorkflowExecutionRepository(session)
        self._workflow_repo = WorkflowRepository(session)
        self._logs = ActivityLogRepository(session)

    # Queueing -----------------------------------------------------------------

    async def queue(
        self,
        data: WorkflowExecutionCreate,
        *,
        requested_by_user_id: uuid.UUID | None = None,
    ) -> WorkflowExecution:
        """Queue a workflow execution for the worker."""
        if data.organization_id is None:
            raise AppError(
                code="execution.organization_required",
                message="organization_id is required",
                status_code=400,
            )

        workflow = await self._workflow_repo.get(data.organization_id, data.workflow_id)
        if workflow is None:
            raise AppError(
                code="workflow.not_found",
                message="Workflow not found",
                status_code=404,
            )
        if workflow.status != WorkflowStatus.ACTIVE:
            raise AppError(
                code="workflow.not_active",
                message="Only active workflows can be queued",
                status_code=400,
            )

        execution = WorkflowExecution(
            organization_id=data.organization_id,
            workflow_id=data.workflow_id,
            trigger_id=data.trigger_id,
            status=ExecutionStatus.QUEUED,
            input=data.input,
            max_attempts=data.max_attempts,
            retry_delay_seconds=data.retry_delay_seconds,
            retry_backoff=data.retry_backoff,
            requested_by_user_id=requested_by_user_id,
            trace_id=data.trace_id or uuid.uuid4(),
        )
        self._repo.add(execution)
        self._logs.add(
            ActivityLog(
                organization_id=data.organization_id,
                user_id=requested_by_user_id,
                event_type=ActivityEventType.EXECUTION_QUEUED,
                entity_type="workflow_execution",
                entity_id=execution.id,
                description=(
                    f"Queued execution for workflow "
                    f"'{workflow.name}' (attempt {(execution.attempts or 0) + 1})"
                ),
                metadata_={"workflow_id": str(data.workflow_id)},
                occurred_at=utcnow(),
            )
        )
        try:
            await self._repo.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise AppError(
                code="execution.create_failed",
                message="Could not create workflow execution",
                status_code=409,
            ) from exc
        await commit_with_retry(self._session)
        return execution

    # Lifecycle state machine --------------------------------------------------

    async def start(self, organization_id: uuid.UUID, execution_id: uuid.UUID) -> WorkflowExecution:
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status != ExecutionStatus.QUEUED:
            raise AppError(
                code="execution.invalid_state",
                message="Only queued executions can be started",
                status_code=409,
            )
        execution.status = ExecutionStatus.RUNNING
        execution.attempts += 1
        execution.started_at = utcnow()
        await commit_with_retry(self._session)
        return execution

    async def complete(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        output: dict,
    ) -> WorkflowExecution:
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status != ExecutionStatus.RUNNING:
            raise AppError(
                code="execution.invalid_state",
                message="Only running executions can be completed",
                status_code=409,
            )
        execution.status = ExecutionStatus.SUCCEEDED
        execution.output = output
        execution.finished_at = utcnow()
        await commit_with_retry(self._session)
        return execution

    async def fail(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        error: dict,
        schedule_retry: bool = True,
    ) -> WorkflowExecution:
        execution = await self._repo.get_or_404(organization_id, execution_id)
        execution.error = error
        if schedule_retry and execution.attempts < execution.max_attempts:
            execution.status = ExecutionStatus.RETRYING
            execution.next_retry_at = utcnow() + timedelta(
                seconds=self._retry_delay_seconds(execution)
            )
        else:
            execution.status = ExecutionStatus.FAILED
            execution.next_retry_at = None
            execution.finished_at = utcnow()
        await commit_with_retry(self._session)
        return execution

    async def retry(self, organization_id: uuid.UUID, execution_id: uuid.UUID) -> WorkflowExecution:
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status not in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
            raise AppError(
                code="execution.invalid_state",
                message="Only failed or cancelled executions can be retried",
                status_code=409,
            )
        execution.status = ExecutionStatus.QUEUED
        execution.next_retry_at = None
        await commit_with_retry(self._session)
        return execution

    async def cancel(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> WorkflowExecution:
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status not in (
            ExecutionStatus.QUEUED,
            ExecutionStatus.RUNNING,
            ExecutionStatus.RETRYING,
        ):
            raise AppError(
                code="execution.invalid_state",
                message="This execution cannot be cancelled",
                status_code=409,
            )
        execution.status = ExecutionStatus.CANCELLED
        execution.finished_at = utcnow()
        await commit_with_retry(self._session)
        return execution

    async def timeout(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> WorkflowExecution:
        execution = await self._repo.get_or_404(organization_id, execution_id)
        execution.status = ExecutionStatus.TIMED_OUT
        execution.error = {"error": "execution timed out"}
        execution.finished_at = utcnow()
        await commit_with_retry(self._session)
        return execution

    @staticmethod
    def _retry_delay_seconds(execution: WorkflowExecution) -> int:
        """Compute the delay before the next retry for an execution."""
        if execution.retry_backoff == "exponential":
            return execution.retry_delay_seconds * (2 ** (execution.attempts - 1))
        return execution.retry_delay_seconds

    # Worker sweep helpers -----------------------------------------------------

    async def get_queued(self, limit: int) -> list[WorkflowExecution]:
        return await self._repo.get_queued(limit)

    async def get_queued_for_retry(
        self, before: datetime | None = None
    ) -> list[WorkflowExecution]:
        if before is not None:
            return await self._repo.get_queued_for_retry(before)
        return await self._repo.get_queued_for_retry()

    async def get_stuck_running(self) -> list[WorkflowExecution]:
        return await self._repo.get_stuck_running()

    # Read APIs -----------------------------------------------------------------

    async def list_executions(
        self,
        organization_id: uuid.UUID,
        *,
        workflow_id: uuid.UUID | None = None,
        trigger_id: uuid.UUID | None = None,
        status: ExecutionStatus | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        return await self._repo.list(
            organization_id,
            workflow_id=workflow_id,
            trigger_id=trigger_id,
            status=status,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )

    async def count_executions(
        self,
        organization_id: uuid.UUID,
        *,
        workflow_id: uuid.UUID | None = None,
        trigger_id: uuid.UUID | None = None,
        status: ExecutionStatus | None = None,
    ) -> int:
        return await self._repo.count(
            organization_id,
            workflow_id=workflow_id,
            trigger_id=trigger_id,
            status=status,
        )

    async def get_execution(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> WorkflowExecution:
        return await self._repo.get_or_404(organization_id, execution_id)
