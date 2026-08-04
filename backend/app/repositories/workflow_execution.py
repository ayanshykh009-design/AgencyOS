"""WorkflowExecution repository (org-scoped CRUD + queue operations)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExecutionStatus
from app.models.workflow_execution import WorkflowExecution

if TYPE_CHECKING:
    pass


_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

# Module-level alias so ``list[...]`` annotations inside the class (which has a
# ``list`` method) resolve to the builtin type, not the shadowing method.
WorkflowExecutionList = list[WorkflowExecution]


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

    async def get_queued_for_retry(
        self, before: datetime | None = None
    ) -> WorkflowExecutionList:
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