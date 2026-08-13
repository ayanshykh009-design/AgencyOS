"""WorkflowExecution repository (org-scoped CRUD + queue operations)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import ExecutionStatus
from app.models.execution_event import ExecutionEvent
from app.models.organization import Organization
from app.models.workflow import Workflow
from app.models.workflow_execution import WorkflowExecution

if TYPE_CHECKING:
    pass


_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

# Module-level alias so ``list[...]`` annotations inside the class (which has a
# ``list`` method) resolve to the builtin type, not the shadowing method.
WorkflowExecutionList = list[WorkflowExecution]
WorkflowOrgList = list[uuid.UUID]
ExecutionEventList = list[ExecutionEvent]
WorkflowQueueStatusList = list[tuple[uuid.UUID, str, int, int, int]]


class WorkflowExecutionRepository:
    """Data access for workflow executions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> WorkflowExecution | None:
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.organization_id == organization_id,
            WorkflowExecution.id == execution_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> WorkflowExecution:
        from app.core.errors import AppError

        execution = await self.get(organization_id, execution_id)
        if execution is None:
            raise AppError(
                code="workflow_execution.not_found",
                message="Workflow execution not found",
                status_code=404,
            )
        return execution

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        workflow_id: uuid.UUID | None = None,
        trigger_id: uuid.UUID | None = None,
        status: ExecutionStatus | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        stmt = select(WorkflowExecution).where(WorkflowExecution.organization_id == organization_id)
        if workflow_id is not None:
            stmt = stmt.where(WorkflowExecution.workflow_id == workflow_id)
        if trigger_id is not None:
            stmt = stmt.where(WorkflowExecution.trigger_id == trigger_id)
        if status is not None:
            stmt = stmt.where(WorkflowExecution.status == status)

        sort_col = getattr(WorkflowExecution, sort, WorkflowExecution.created_at)
        if order == "desc":
            sort_col = sort_col.desc()
        stmt = stmt.order_by(sort_col).limit(min(limit, _MAX_PAGE_SIZE)).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        organization_id: uuid.UUID,
        *,
        workflow_id: uuid.UUID | None = None,
        trigger_id: uuid.UUID | None = None,
        status: ExecutionStatus | None = None,
    ) -> int:
        stmt = (
            select(func.count(WorkflowExecution.id))
            .where(WorkflowExecution.organization_id == organization_id)
            .select_from(WorkflowExecution)
        )
        if workflow_id is not None:
            stmt = stmt.where(WorkflowExecution.workflow_id == workflow_id)
        if trigger_id is not None:
            stmt = stmt.where(WorkflowExecution.trigger_id == trigger_id)
        if status is not None:
            stmt = stmt.where(WorkflowExecution.status == status)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def add(self, execution: WorkflowExecution) -> None:
        self._session.add(execution)

    async def delete(self, organization_id: uuid.UUID, execution_id: uuid.UUID) -> bool:
        execution = await self.get(organization_id, execution_id)
        if execution is None:
            return False
        await self._session.delete(execution)
        return True

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, execution: WorkflowExecution) -> None:
        await self._session.refresh(execution)

    # Queue operations ---------------------------------------------------------

    async def count_pending(self, organization_id: uuid.UUID) -> int:
        """Count un-drained executions (QUEUED + RETRYING) for an organization."""
        stmt = (
            select(func.count(WorkflowExecution.id))
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.status.in_((ExecutionStatus.QUEUED, ExecutionStatus.RETRYING)),
            )
            .select_from(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_pending_all_orgs(self) -> int:
        """Count QUEUED + RETRYING executions across all organizations."""
        stmt = (
            select(func.count(WorkflowExecution.id))
            .where(WorkflowExecution.status.in_((ExecutionStatus.QUEUED, ExecutionStatus.RETRYING)))
            .select_from(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_status(self, status: ExecutionStatus) -> int:
        """Count executions in a given status across all organizations."""
        stmt = (
            select(func.count(WorkflowExecution.id))
            .where(WorkflowExecution.status == status)
            .select_from(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_by_status_and_date(self, status: ExecutionStatus, cutoff: datetime) -> int:
        """Count executions created after ``cutoff`` in a given status."""
        stmt = (
            select(func.count(WorkflowExecution.id))
            .where(
                WorkflowExecution.status == status,
                WorkflowExecution.created_at >= cutoff,
            )
            .select_from(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_by_workflow(self, cutoff: datetime, limit: int = 50) -> dict[str, int]:
        """Count executions created after ``cutoff`` grouped by workflow name."""
        stmt = (
            select(Workflow.name, func.count(WorkflowExecution.id))
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .where(WorkflowExecution.created_at >= cutoff)
            .group_by(Workflow.name)
            .order_by(func.count(WorkflowExecution.id).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return {name: int(count) for name, count in result.all()}

    async def count_by_organization(self, cutoff: datetime, limit: int = 50) -> dict[str, int]:
        """Count executions created after ``cutoff`` grouped by organization name."""
        stmt = (
            select(Organization.name, func.count(WorkflowExecution.id))
            .join(Organization, Organization.id == WorkflowExecution.organization_id)
            .where(WorkflowExecution.created_at >= cutoff)
            .group_by(Organization.name)
            .order_by(func.count(WorkflowExecution.id).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return {name: int(count) for name, count in result.all()}

    async def list_history(
        self,
        *,
        cutoff: datetime,
        status: ExecutionStatus | None = None,
        workflow_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> WorkflowExecutionList:
        """List executions created after ``cutoff`` across all organizations.

        Joins workflow names and requested-by users eagerly so the calling
        service can serialize rows without extra async IO.
        """
        stmt = (
            select(WorkflowExecution)
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .options(
                selectinload(WorkflowExecution.workflow),
                selectinload(WorkflowExecution.trigger),
                selectinload(WorkflowExecution.requested_by),
            )
            .where(WorkflowExecution.created_at >= cutoff)
            .order_by(WorkflowExecution.created_at.desc())
            .limit(min(limit, _MAX_PAGE_SIZE))
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(WorkflowExecution.status == status)
        if workflow_name is not None:
            stmt = stmt.where(Workflow.name.ilike(f"%{workflow_name}%"))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_history(
        self,
        *,
        cutoff: datetime,
        status: ExecutionStatus | None = None,
        workflow_name: str | None = None,
    ) -> int:
        """Count executions created after ``cutoff`` across all organizations."""
        stmt = (
            select(func.count(WorkflowExecution.id))
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .where(WorkflowExecution.created_at >= cutoff)
            .select_from(WorkflowExecution)
        )
        if status is not None:
            stmt = stmt.where(WorkflowExecution.status == status)
        if workflow_name is not None:
            stmt = stmt.where(Workflow.name.ilike(f"%{workflow_name}%"))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_timeline(
        self,
        *,
        cutoff: datetime,
        status: ExecutionStatus | None = None,
        workflow_name: str | None = None,
        limit: int = 100,
    ) -> ExecutionEventList:
        """List execution timeline events across all organizations.

        Joins the owning execution and workflow so each event can be
        serialized with workflow name and execution status/duration.
        """
        stmt = (
            select(ExecutionEvent)
            .join(WorkflowExecution, WorkflowExecution.id == ExecutionEvent.execution_id)
            .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
            .options(
                selectinload(ExecutionEvent.execution),
                selectinload(ExecutionEvent.workflow),
            )
            .where(ExecutionEvent.occurred_at >= cutoff)
            .order_by(ExecutionEvent.occurred_at.desc())
            .limit(min(limit, 500))
        )
        if status is not None:
            stmt = stmt.where(WorkflowExecution.status == status)
        if workflow_name is not None:
            stmt = stmt.where(Workflow.name.ilike(f"%{workflow_name}%"))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def queue_status(self, limit: int = 100) -> WorkflowQueueStatusList:
        """Per-organization queue metrics: (org_id, name, queued, running, pending).

        Only organizations with at least one QUEUED/RUNNING/RETRYING execution
        are returned, ordered by queued volume descending.
        """
        queued = (
            select(func.count(WorkflowExecution.id))
            .where(
                WorkflowExecution.organization_id == Organization.id,
                WorkflowExecution.status == ExecutionStatus.QUEUED,
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        running = (
            select(func.count(WorkflowExecution.id))
            .where(
                WorkflowExecution.organization_id == Organization.id,
                WorkflowExecution.status == ExecutionStatus.RUNNING,
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        pending = (
            select(func.count(WorkflowExecution.id))
            .where(
                WorkflowExecution.organization_id == Organization.id,
                WorkflowExecution.status.in_((ExecutionStatus.QUEUED, ExecutionStatus.RETRYING)),
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        stmt = (
            select(Organization.id, Organization.name, queued, running, pending)
            .where((queued > 0) | (running > 0) | (pending > 0))
            .order_by(queued.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            (org_id, str(name), int(queued), int(running), int(pending))
            for org_id, name, queued, running, pending in rows
        ]

    async def get_queued(self, limit: int) -> WorkflowExecutionList:
        """Get QUEUED executions across all organizations (worker drain)."""
        stmt = (
            select(WorkflowExecution)
            .where(WorkflowExecution.status == ExecutionStatus.QUEUED)
            .order_by(WorkflowExecution.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_queued_orgs(self, limit: int) -> WorkflowOrgList:
        """Fair-drain candidates: orgs with QUEUED work, oldest-first.

        ``GROUP BY organization_id ORDER BY MIN(created_at)`` guarantees an org
        that has been waiting longest is visited first, so one busy org cannot
        starve everyone else's queue.
        """
        stmt = (
            select(WorkflowExecution.organization_id)
            .where(WorkflowExecution.status == ExecutionStatus.QUEUED)
            .group_by(WorkflowExecution.organization_id)
            .order_by(func.min(WorkflowExecution.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_queued_for_org(
        self, organization_id: uuid.UUID, limit: int
    ) -> WorkflowExecutionList:
        """Get the oldest QUEUED executions for one organization."""
        stmt = (
            select(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.status == ExecutionStatus.QUEUED,
            )
            .order_by(WorkflowExecution.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_queued_for_retry(self, before: datetime | None = None) -> WorkflowExecutionList:
        """Get RETRYING executions whose next_retry_at has arrived."""
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.status == ExecutionStatus.RETRYING,
            WorkflowExecution.next_retry_at.is_not(None),
        )
        if before is not None:
            stmt = stmt.where(WorkflowExecution.next_retry_at <= before)
        stmt = stmt.order_by(WorkflowExecution.next_retry_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stuck_running(self) -> WorkflowExecutionList:
        """Get RUNNING executions that have exceeded the timeout (stale)."""
        from app.core.config import settings

        cutoff = datetime.now(UTC) - timedelta(seconds=settings.EXECUTION_TIMEOUT_SECONDS)
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.status == ExecutionStatus.RUNNING,
            WorkflowExecution.started_at.is_not(None),
            WorkflowExecution.started_at < cutoff,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_trace_id(
        self, organization_id: uuid.UUID, trace_id: uuid.UUID
    ) -> WorkflowExecution | None:
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.organization_id == organization_id,
            WorkflowExecution.trace_id == trace_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # Guarded state transitions -------------------------------------------------
    #
    # Every transition below is a single conditional UPDATE .. RETURNING so the
    # row-level WHERE is re-evaluated against the latest committed row (Postgres
    # READ COMMITTED + EvalPlanQual). A concurrent worker or cancel can never
    # clobber a transition; callers receive the updated row or ``None``.

    async def mark_started(
        self, organization_id: uuid.UUID, execution_id: uuid.UUID
    ) -> WorkflowExecution | None:
        """QUEUED + no cancel flag -> RUNNING, attempts bumped. Returns row or None."""
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status == ExecutionStatus.QUEUED,
                WorkflowExecution.cancel_requested_at.is_(None),
            )
            .values(
                status=ExecutionStatus.RUNNING,
                attempts=WorkflowExecution.attempts + 1,
                started_at=func.now(),
            )
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_succeeded(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        output: dict,
        finished_at: datetime,
    ) -> WorkflowExecution | None:
        """RUNNING + no cancel flag -> SUCCEEDED. Returns row or None."""
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status == ExecutionStatus.RUNNING,
                WorkflowExecution.cancel_requested_at.is_(None),
            )
            .values(
                status=ExecutionStatus.SUCCEEDED,
                output=output,
                finished_at=finished_at,
            )
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_failed(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        error: dict,
        to_status: ExecutionStatus,
        next_retry_at: datetime | None,
        finished_at: datetime | None,
    ) -> WorkflowExecution | None:
        """RUNNING + no cancel flag -> FAILED or RETRYING. Returns row or None."""
        values: dict = {
            "status": to_status,
            "error": error,
            "next_retry_at": next_retry_at,
        }
        if finished_at is not None:
            values["finished_at"] = finished_at
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status == ExecutionStatus.RUNNING,
                WorkflowExecution.cancel_requested_at.is_(None),
            )
            .values(**values)
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_failed_if_queued(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        error: dict,
        finished_at: datetime,
    ) -> WorkflowExecution | None:
        """QUEUED -> FAILED (workflow became unavailable before dispatch)."""
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status == ExecutionStatus.QUEUED,
            )
            .values(
                status=ExecutionStatus.FAILED,
                error=error,
                next_retry_at=None,
                finished_at=finished_at,
            )
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancelled_after_run(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        finished_at: datetime,
    ) -> WorkflowExecution | None:
        """RUNNING with a cancel flag -> CANCELLED. Returns row or None."""
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status == ExecutionStatus.RUNNING,
                WorkflowExecution.cancel_requested_at.is_not(None),
            )
            .values(
                status=ExecutionStatus.CANCELLED,
                finished_at=finished_at,
            )
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancelled_if_pending(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        cancel_requested_at: datetime,
        cancelled_by_user_id: uuid.UUID | None,
        finished_at: datetime,
    ) -> WorkflowExecution | None:
        """QUEUED/RETRYING + no cancel flag -> CANCELLED. Returns row or None."""
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status.in_((ExecutionStatus.QUEUED, ExecutionStatus.RETRYING)),
                WorkflowExecution.cancel_requested_at.is_(None),
            )
            .values(
                status=ExecutionStatus.CANCELLED,
                cancel_requested_at=cancel_requested_at,
                cancelled_by_user_id=cancelled_by_user_id,
                finished_at=finished_at,
            )
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_cancel_requested(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        cancel_requested_at: datetime,
        cancelled_by_user_id: uuid.UUID | None,
    ) -> WorkflowExecution | None:
        """RUNNING + no cancel flag: flag the row for in-flight cancellation."""
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status == ExecutionStatus.RUNNING,
                WorkflowExecution.cancel_requested_at.is_(None),
            )
            .values(
                cancel_requested_at=cancel_requested_at,
                cancelled_by_user_id=cancelled_by_user_id,
            )
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_timed_out(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        *,
        error: dict,
        finished_at: datetime,
    ) -> WorkflowExecution | None:
        """RUNNING + no cancel flag -> TIMED_OUT (terminal, no auto-retry)."""
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status == ExecutionStatus.RUNNING,
                WorkflowExecution.cancel_requested_at.is_(None),
            )
            .values(
                status=ExecutionStatus.TIMED_OUT,
                error=error,
                finished_at=finished_at,
            )
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_requeued(
        self,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
    ) -> WorkflowExecution | None:
        """FAILED/CANCELLED/TIMED_OUT -> QUEUED, clearing any cancel flag."""
        stmt = (
            update(WorkflowExecution)
            .where(
                WorkflowExecution.organization_id == organization_id,
                WorkflowExecution.id == execution_id,
                WorkflowExecution.status.in_(
                    (
                        ExecutionStatus.FAILED,
                        ExecutionStatus.CANCELLED,
                        ExecutionStatus.TIMED_OUT,
                    )
                ),
            )
            .values(
                status=ExecutionStatus.QUEUED,
                next_retry_at=None,
                cancel_requested_at=None,
                cancelled_by_user_id=None,
            )
            .returning(WorkflowExecution)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
