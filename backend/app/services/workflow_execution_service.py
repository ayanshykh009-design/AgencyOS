"""WorkflowExecution service: queue management, execution, retry."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.metrics import get_counter, get_histogram
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, ExecutionEventType, ExecutionStatus, WorkflowStatus
from app.models.workflow_execution import WorkflowExecution
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.workflow import WorkflowRepository
from app.repositories.workflow_execution import WorkflowExecutionRepository
from app.schemas.workflow_execution import WorkflowExecutionCreate
from app.services.automation_control_service import AutomationControlService
from app.services.base import commit_with_retry, utcnow
from app.services.execution_event_service import ExecutionEventService


class WorkflowExecutionService:
    """Owns execution lifecycle and queue operations.

    All state transitions are guarded single ``UPDATE ... RETURNING``
    statements (see ``WorkflowExecutionRepository``), so concurrent workers and
    cancels can never clobber each other: the row-level WHERE is re-checked
    against the latest committed state.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = WorkflowExecutionRepository(session)
        self._workflow_repo = WorkflowRepository(session)
        self._logs = ActivityLogRepository(session)
        self._events = ExecutionEventService(session)
        self._automation_control = AutomationControlService(session)

    # Audit + timeline helpers ------------------------------------------------

    @staticmethod
    def _duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
        """Elapsed wall-clock time between started and finished, in ms."""
        if started_at is None or finished_at is None:
            return None
        return int((finished_at - started_at).total_seconds() * 1000)

    def _record_duration(self, status: ExecutionStatus, duration_ms: int | None) -> None:
        """Record the execution duration histogram (best-effort, per status)."""
        if duration_ms is None:
            return
        get_histogram(
            "execution_duration_seconds",
            description="Workflow execution duration by terminal status",
            unit="s",
        ).observe(duration_ms / 1000, {"status": status.value})

    def _audit(
        self,
        execution: WorkflowExecution,
        *,
        event_type: ActivityEventType,
        description: str,
        actor_user_id: uuid.UUID | None = None,
        duration_ms: int | None = None,
        **extra: object,
    ) -> None:
        """Write one append-only business audit record for an execution."""
        metadata: dict[str, object] = {
            "execution_id": str(execution.id),
            "workflow_id": str(execution.workflow_id),
            "trigger_id": str(execution.trigger_id) if execution.trigger_id else None,
            "actor": str(actor_user_id) if actor_user_id else None,
            "duration_ms": duration_ms,
            **extra,
        }
        self._logs.add(
            ActivityLog(
                organization_id=execution.organization_id,
                user_id=actor_user_id,
                event_type=event_type,
                entity_type="workflow_execution",
                entity_id=execution.id,
                description=description,
                metadata_=metadata,
                occurred_at=utcnow(),
            )
        )

    async def _timeline(
        self,
        execution: WorkflowExecution,
        event_type: ExecutionEventType,
        **metadata: object,
    ) -> None:
        """Best-effort append to the technical execution timeline."""
        await self._events.record(
            organization_id=execution.organization_id,
            workflow_id=execution.workflow_id,
            execution_id=execution.id,
            attempt=execution.attempts,
            event_type=event_type,
            metadata=metadata or None,
        )

    async def record_event(
        self,
        execution: WorkflowExecution,
        event_type: ExecutionEventType,
        **metadata: object,
    ) -> None:
        """Best-effort timeline write from worker/adapter boundaries."""
        await self._timeline(execution, event_type, **metadata)

    async def record_events(
        self,
        execution: WorkflowExecution,
        events: list[tuple[ExecutionEventType, dict[str, object]]],
    ) -> None:
        """Best-effort batched timeline write from adapter step hooks."""
        await self._events.record_many(
            organization_id=execution.organization_id,
            workflow_id=execution.workflow_id,
            execution_id=execution.id,
            attempt=execution.attempts,
            events=events,
        )

    # Queueing -----------------------------------------------------------------

    async def queue(
        self,
        data: WorkflowExecutionCreate,
        *,
        requested_by_user_id: uuid.UUID | None = None,
        bypass_pending_cap: bool = False,
    ) -> WorkflowExecution:
        """Queue a workflow execution for the worker.

        ``bypass_pending_cap`` is set by the API when the caller holds
        ``EXECUTION_MANAGE``; the cap otherwise bounds un-drained work per org.
        """
        await self._automation_control.block_queue_if_paused()

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

        pending = await self._repo.count_pending(data.organization_id)
        if not bypass_pending_cap and pending >= settings.EXECUTION_MAX_PENDING_PER_ORG:
            raise AppError(
                code="execution.pending_cap_exceeded",
                message=(
                    "Organization has too many pending executions "
                    f"({settings.EXECUTION_MAX_PENDING_PER_ORG} max)"
                ),
                status_code=409,
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
            idempotency_key=data.idempotency_key,
        )
        self._repo.add(execution)
        self._audit(
            execution,
            event_type=ActivityEventType.EXECUTION_QUEUED,
            description=(
                f"Queued execution for workflow "
                f"'{workflow.name}' (attempt {(execution.attempts or 0) + 1})"
            ),
            actor_user_id=requested_by_user_id,
            trigger_id=str(data.trigger_id) if data.trigger_id else None,
        )
        try:
            await self._repo.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise AppError(
                code="execution.duplicate_idempotency_key"
                if data.idempotency_key
                else "execution.create_failed",
                message=(
                    "An execution with this idempotency key already exists"
                    if data.idempotency_key
                    else "Could not create workflow execution"
                ),
                status_code=409,
            ) from exc
        await self._timeline(
            execution,
            ExecutionEventType.QUEUED,
            trigger_id=str(data.trigger_id) if data.trigger_id else None,
            actor=str(requested_by_user_id) if requested_by_user_id else None,
        )
        await commit_with_retry(self._session)
        get_counter(
            "execution_queued_total",
            description="Workflow executions queued for the worker",
        ).add()
        return execution

    # Lifecycle state machine --------------------------------------------------

    async def start(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> WorkflowExecution:
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status != ExecutionStatus.QUEUED:
            raise AppError(
                code="execution.invalid_state",
                message="Only queued executions can be started",
                status_code=409,
            )
        updated = await self._repo.mark_started(organization_id, execution_id)
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="execution.invalid_state",
                message="Execution was cancelled or claimed by another worker",
                status_code=409,
            )
        self._audit(
            updated,
            event_type=ActivityEventType.EXECUTION_STARTED,
            description=f"Execution started (attempt {updated.attempts})",
            actor_user_id=actor_user_id,
        )
        await self._timeline(
            updated,
            ExecutionEventType.STARTED,
            actor=str(actor_user_id) if actor_user_id else None,
        )
        await commit_with_retry(self._session)
        return updated

    async def complete(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        output: dict,
        actor_user_id: uuid.UUID | None = None,
    ) -> WorkflowExecution:
        self._assert_payload_size(output, "output")
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status != ExecutionStatus.RUNNING:
            raise AppError(
                code="execution.invalid_state",
                message="Only running executions can be completed",
                status_code=409,
            )
        finished_at = utcnow()
        updated = await self._repo.mark_succeeded(
            organization_id, execution_id, output=output, finished_at=finished_at
        )
        if updated is None:
            # A concurrent cancel flagged the run — honour it.
            updated = await self._repo.mark_cancelled_after_run(
                organization_id, execution_id, finished_at=finished_at
            )
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="execution.invalid_state",
                message="Execution state changed concurrently",
                status_code=409,
            )
        duration_ms = self._duration_ms(updated.started_at, finished_at)
        if updated.status == ExecutionStatus.CANCELLED:
            self._audit(
                updated,
                event_type=ActivityEventType.EXECUTION_CANCELLED,
                description="Execution cancelled while running",
                duration_ms=duration_ms,
            )
            await self._timeline(
                updated,
                ExecutionEventType.CANCELLED,
                duration_ms=duration_ms,
                actor=str(updated.cancelled_by_user_id)
                if updated.cancelled_by_user_id
                else None,
            )
        else:
            self._audit(
                updated,
                event_type=ActivityEventType.EXECUTION_COMPLETED,
                description="Execution completed successfully",
                actor_user_id=actor_user_id,
                duration_ms=duration_ms,
            )
            await self._timeline(
                updated,
                ExecutionEventType.SUCCEEDED,
                duration_ms=duration_ms,
            )
        self._record_duration(updated.status, duration_ms)
        await commit_with_retry(self._session)
        return updated

    async def fail(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        error: dict,
        schedule_retry: bool = True,
        actor_user_id: uuid.UUID | None = None,
    ) -> WorkflowExecution:
        self._assert_payload_size(error, "error")
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status != ExecutionStatus.RUNNING:
            raise AppError(
                code="execution.invalid_state",
                message="Only running executions can be failed",
                status_code=409,
            )
        finished_at = utcnow()
        if execution.cancel_requested_at is not None:
            updated = await self._repo.mark_cancelled_after_run(
                organization_id, execution_id, finished_at=finished_at
            )
            if updated is None:
                await self._session.rollback()
                raise AppError(
                    code="execution.invalid_state",
                    message="Execution state changed concurrently",
                    status_code=409,
                )
            duration_ms = self._duration_ms(updated.started_at, finished_at)
            self._audit(
                updated,
                event_type=ActivityEventType.EXECUTION_CANCELLED,
                description="Execution cancelled while running",
                duration_ms=duration_ms,
            )
            await self._timeline(
                updated,
                ExecutionEventType.CANCELLED,
                duration_ms=duration_ms,
                actor=str(updated.cancelled_by_user_id)
                if updated.cancelled_by_user_id
                else None,
            )
            self._record_duration(ExecutionStatus.CANCELLED, duration_ms)
            get_counter(
                "execution_cancelled_total",
                description="Workflow executions cancelled",
            ).add()
            await commit_with_retry(self._session)
            return updated

        if schedule_retry and execution.attempts < execution.max_attempts:
            to_status = ExecutionStatus.RETRYING
            next_retry_at = utcnow() + timedelta(seconds=self._retry_delay_seconds(execution))
        else:
            to_status = ExecutionStatus.FAILED
            next_retry_at = None
        updated = await self._repo.mark_failed(
            organization_id,
            execution_id,
            error=error,
            to_status=to_status,
            next_retry_at=next_retry_at,
            finished_at=finished_at if to_status == ExecutionStatus.FAILED else None,
        )
        if updated is None:
            updated = await self._repo.mark_cancelled_after_run(
                organization_id, execution_id, finished_at=finished_at
            )
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="execution.invalid_state",
                message="Execution state changed concurrently",
                status_code=409,
            )
        duration_ms = self._duration_ms(updated.started_at, finished_at)
        if updated.status == ExecutionStatus.CANCELLED:
            self._audit(
                updated,
                event_type=ActivityEventType.EXECUTION_CANCELLED,
                description="Execution cancelled while running",
                duration_ms=duration_ms,
            )
            await self._timeline(
                updated,
                ExecutionEventType.CANCELLED,
                duration_ms=duration_ms,
                actor=str(updated.cancelled_by_user_id)
                if updated.cancelled_by_user_id
                else None,
            )
        else:
            error_code = error.get("error") if isinstance(error, dict) else None
            self._audit(
                updated,
                event_type=ActivityEventType.EXECUTION_FAILED,
                description=(
                    "Execution failed; retry scheduled"
                    if to_status == ExecutionStatus.RETRYING
                    else "Execution failed"
                ),
                actor_user_id=actor_user_id,
                duration_ms=duration_ms,
                error_code=str(error_code) if error_code else None,
            )
            await self._timeline(
                updated,
                ExecutionEventType.RETRYING
                if to_status == ExecutionStatus.RETRYING
                else ExecutionEventType.FAILED,
                duration_ms=duration_ms,
                error_code=str(error_code) if error_code else None,
            )
            if to_status == ExecutionStatus.FAILED:
                get_counter(
                    "execution_failed_total",
                    description="Workflow executions that failed terminally",
                ).add()
        self._record_duration(updated.status, duration_ms)
        await commit_with_retry(self._session)
        return updated

    async def fail_queued(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        error: dict,
    ) -> WorkflowExecution:
        """Fail a QUEUED execution without dispatching (workflow unavailable)."""
        self._assert_payload_size(error, "error")
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status != ExecutionStatus.QUEUED:
            raise AppError(
                code="execution.invalid_state",
                message="Only queued executions can be failed before dispatch",
                status_code=409,
            )
        updated = await self._repo.mark_failed_if_queued(
            organization_id, execution_id, error=error, finished_at=utcnow()
        )
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="execution.invalid_state",
                message="Execution state changed concurrently",
                status_code=409,
            )
        self._audit(
            updated,
            event_type=ActivityEventType.EXECUTION_FAILED,
            description="Execution failed before dispatch (workflow unavailable)",
            error_code=error.get("error") if isinstance(error, dict) else None,
        )
        await self._timeline(
            updated,
            ExecutionEventType.FAILED,
            error_code=error.get("error") if isinstance(error, dict) else None,
        )
        get_counter(
            "execution_failed_total",
            description="Workflow executions that failed terminally",
        ).add()
        await commit_with_retry(self._session)
        return updated

    async def retry(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
    ) -> WorkflowExecution:
        await self._automation_control.block_execution_if_paused()

        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status not in (
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.TIMED_OUT,
        ):
            raise AppError(
                code="execution.invalid_state",
                message="Only failed, cancelled, or timed-out executions can be retried",
                status_code=409,
            )
        updated = await self._repo.mark_requeued(organization_id, execution_id)
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="execution.invalid_state",
                message="Execution state changed concurrently",
                status_code=409,
            )
        self._audit(
            updated,
            event_type=ActivityEventType.EXECUTION_RETRIED,
            description=f"Execution retried (attempt {updated.attempts + 1})",
            actor_user_id=actor_user_id,
        )
        await self._timeline(
            updated,
            ExecutionEventType.RETRYING,
            actor=str(actor_user_id) if actor_user_id else None,
        )
        get_counter(
            "execution_retried_total",
            description="Workflow executions requeued for retry",
        ).add()
        await commit_with_retry(self._session)
        return updated

    async def cancel(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        cancelled_by_user_id: uuid.UUID | None = None,
    ) -> WorkflowExecution:
        """Cancel an execution.

        QUEUED/RETRYING are transitioned to CANCELLED immediately. A RUNNING
        execution is only flagged (``cancel_requested_at``): the worker honours
        the flag when the adapter returns and lands on CANCELLED, so an
        in-flight run is never left half-finished or wrongly marked succeeded.
        """
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status == ExecutionStatus.CANCELLED:
            return execution
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
        finished_at = utcnow()
        if execution.status in (ExecutionStatus.QUEUED, ExecutionStatus.RETRYING):
            updated = await self._repo.mark_cancelled_if_pending(
                organization_id,
                execution_id,
                cancel_requested_at=finished_at,
                cancelled_by_user_id=cancelled_by_user_id,
                finished_at=finished_at,
            )
            if updated is None:
                updated = await self._repo.mark_cancel_requested(
                    organization_id,
                    execution_id,
                    cancel_requested_at=finished_at,
                    cancelled_by_user_id=cancelled_by_user_id,
                )
        else:
            updated = await self._repo.mark_cancel_requested(
                organization_id,
                execution_id,
                cancel_requested_at=finished_at,
                cancelled_by_user_id=cancelled_by_user_id,
            )
        if updated is None:
            updated = await self._repo.get(organization_id, execution_id)
            if updated is None:
                raise AppError(
                    code="execution.not_found",
                    message="Workflow execution not found",
                    status_code=404,
                )
        if updated.status == ExecutionStatus.CANCELLED:
            self._audit(
                updated,
                event_type=ActivityEventType.EXECUTION_CANCELLED,
                description="Execution cancelled",
                actor_user_id=cancelled_by_user_id,
                duration_ms=self._duration_ms(updated.started_at, finished_at),
            )
            await self._timeline(
                updated,
                ExecutionEventType.CANCELLED,
                actor=str(cancelled_by_user_id) if cancelled_by_user_id else None,
            )
            self._record_duration(
                ExecutionStatus.CANCELLED,
                self._duration_ms(updated.started_at, finished_at),
            )
            get_counter(
                "execution_cancelled_total",
                description="Workflow executions cancelled",
            ).add()
        await commit_with_retry(self._session)
        return updated

    async def timeout(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> WorkflowExecution:
        execution = await self._repo.get_or_404(organization_id, execution_id)
        if execution.status != ExecutionStatus.RUNNING:
            raise AppError(
                code="execution.invalid_state",
                message="Only running executions can be timed out",
                status_code=409,
            )
        error = {"error": "execution timed out"}
        updated = await self._repo.mark_timed_out(
            organization_id, execution_id, error=error, finished_at=utcnow()
        )
        if updated is None:
            updated = await self._repo.mark_cancelled_after_run(
                organization_id, execution_id, finished_at=utcnow()
            )
        if updated is None:
            await self._session.rollback()
            raise AppError(
                code="execution.invalid_state",
                message="Execution state changed concurrently",
                status_code=409,
            )
        if updated.status == ExecutionStatus.CANCELLED:
            await self._timeline(
                updated,
                ExecutionEventType.CANCELLED,
                duration_ms=self._duration_ms(updated.started_at, updated.finished_at),
            )
            self._record_duration(
                ExecutionStatus.CANCELLED,
                self._duration_ms(updated.started_at, updated.finished_at),
            )
            get_counter(
                "execution_cancelled_total",
                description="Workflow executions cancelled",
            ).add()
        else:
            await self._timeline(
                updated,
                ExecutionEventType.TIMED_OUT,
                duration_ms=self._duration_ms(updated.started_at, updated.finished_at),
            )
            self._record_duration(
                ExecutionStatus.TIMED_OUT,
                self._duration_ms(updated.started_at, updated.finished_at),
            )
            get_counter(
                "execution_timed_out_total",
                description="Workflow executions that timed out",
            ).add()
        await commit_with_retry(self._session)
        return updated

    @staticmethod
    def _assert_payload_size(payload: dict, field: str) -> None:
        """Reject payloads above the shared result-size cap (413)."""
        size = len(
            json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        )
        if size > settings.BUILTIN_MAX_RESULT_SIZE_BYTES:
            raise AppError(
                code="execution.payload_too_large",
                message=(
                    f"{field} payload exceeds the maximum size "
                    f"({settings.BUILTIN_MAX_RESULT_SIZE_BYTES} bytes)"
                ),
                status_code=413,
            )

    @staticmethod
    def _retry_delay_seconds(execution: WorkflowExecution) -> int:
        """Compute the delay before the next retry for an execution."""
        if execution.retry_backoff == "exponential":
            return execution.retry_delay_seconds * (2 ** (execution.attempts - 1))
        return execution.retry_delay_seconds

    # Worker sweep helpers -----------------------------------------------------

    async def get_queued(self, limit: int) -> list[WorkflowExecution]:
        return await self._repo.get_queued(limit)

    async def get_queued_orgs(self, limit: int) -> list[uuid.UUID]:
        return await self._repo.get_queued_orgs(limit)

    async def get_queued_for_org(
        self, organization_id: uuid.UUID, limit: int
    ) -> list[WorkflowExecution]:
        return await self._repo.get_queued_for_org(organization_id, limit)

    async def count_pending(self, organization_id: uuid.UUID) -> int:
        return await self._repo.count_pending(organization_id)

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
