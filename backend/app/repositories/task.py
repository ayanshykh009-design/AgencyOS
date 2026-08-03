"""Task repository: org-scoped data access with filters and a reminder sweep."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

_OPEN_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS)


class TaskRepository:
    """Data access for tasks (tenant-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, task: Task) -> None:
        self._session.add(task)

    async def delete(self, task: Task) -> None:
        await self._session.delete(task)

    async def get(self, organization_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        stmt = select(Task).where(
            Task.organization_id == organization_id,
            Task.id == task_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> Task:
        task = await self.get(organization_id, task_id)
        if task is None:
            raise AppError(
                code="task.not_found",
                message="Task not found",
                status_code=404,
            )
        return task

    async def list_tasks(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID | None = None,
        assignee_user_id: uuid.UUID | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        due_before: datetime | None = None,
        due_after: datetime | None = None,
        sort: str = "due_at",
        order: str = "asc",
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Task]:
        """Return org-scoped tasks matching the given filters."""
        stmt = self._filtered(
            organization_id,
            lead_id=lead_id,
            assignee_user_id=assignee_user_id,
            status=status,
            priority=priority,
            due_before=due_before,
            due_after=due_after,
        )
        column = getattr(Task, sort, Task.due_at)
        order_col = column.asc() if order == "asc" else column.desc()
        stmt = stmt.order_by(order_col, Task.created_at).limit(
            min(limit, _MAX_PAGE_SIZE)
        ).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_tasks(
        self,
        organization_id: uuid.UUID,
        *,
        query: str,
        limit: int = _DEFAULT_PAGE_SIZE,
    ) -> list[Task]:
        """Return tasks whose title or description matches ``query``."""
        like = f"%{query}%"
        stmt = (
            select(Task)
            .where(
                Task.organization_id == organization_id,
                or_(Task.title.ilike(like), Task.description.ilike(like)),
            )
            .order_by(Task.created_at.desc())
            .limit(min(limit, _MAX_PAGE_SIZE))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID | None = None,
        assignee_user_id: uuid.UUID | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        due_before: datetime | None = None,
        due_after: datetime | None = None,
    ) -> int:
        """Count tasks matching the same filters as :meth:`list`."""
        stmt = (
            self._filtered(
                organization_id,
                lead_id=lead_id,
                assignee_user_id=assignee_user_id,
                status=status,
                priority=priority,
                due_before=due_before,
                due_after=due_after,
            )
            .with_only_columns(func.count(Task.id))
            .order_by(None)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_due_for_reminder(
        self,
        organization_id: uuid.UUID,
        *,
        before: datetime,
        limit: int = 500,
    ) -> list[Task]:
        """Return open tasks whose reminder time has arrived (newest first)."""
        stmt = (
            select(Task)
            .where(
                Task.organization_id == organization_id,
                Task.reminder_at.is_not(None),
                Task.reminder_at <= before,
                Task.status.in_(_OPEN_STATUSES),
            )
            .order_by(Task.reminder_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_open(self, organization_id: uuid.UUID) -> int:
        """Count tasks that are still open (todo or in_progress)."""
        stmt = (
            select(func.count(Task.id))
            .where(
                Task.organization_id == organization_id,
                Task.status.in_(_OPEN_STATUSES),
            )
            .select_from(Task)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_overdue(
        self, organization_id: uuid.UUID, *, before: datetime
    ) -> int:
        """Count open tasks whose due date has passed."""
        stmt = (
            select(func.count(Task.id))
            .where(
                Task.organization_id == organization_id,
                Task.due_at.is_not(None),
                Task.due_at < before,
                Task.status.in_(_OPEN_STATUSES),
            )
            .select_from(Task)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_due_between(
        self,
        organization_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        """Count open tasks due within a window (e.g. today)."""
        stmt = (
            select(func.count(Task.id))
            .where(
                Task.organization_id == organization_id,
                Task.due_at.is_not(None),
                Task.due_at >= start,
                Task.due_at < end,
                Task.status.in_(_OPEN_STATUSES),
            )
            .select_from(Task)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_completed_since(
        self, organization_id: uuid.UUID, *, since: datetime
    ) -> int:
        """Count tasks completed at or after ``since``."""
        stmt = (
            select(func.count(Task.id))
            .where(
                Task.organization_id == organization_id,
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at.is_not(None),
                Task.completed_at >= since,
            )
            .select_from(Task)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def _filtered(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID | None,
        assignee_user_id: uuid.UUID | None,
        status: TaskStatus | None,
        priority: TaskPriority | None,
        due_before: datetime | None,
        due_after: datetime | None,
    ):
        stmt = select(Task).where(Task.organization_id == organization_id)
        if lead_id is not None:
            stmt = stmt.where(Task.lead_id == lead_id)
        if assignee_user_id is not None:
            stmt = stmt.where(Task.assignee_user_id == assignee_user_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)
        if due_before is not None:
            stmt = stmt.where(Task.due_at.is_not(None), Task.due_at <= due_before)
        if due_after is not None:
            stmt = stmt.where(Task.due_at.is_not(None), Task.due_at >= due_after)
        return stmt
