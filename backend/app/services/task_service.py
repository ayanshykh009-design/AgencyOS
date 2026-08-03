"""Task service: CRUD, completion, recurrence, and reminder sweeps.

Tasks are org-scoped to-dos optionally linked to a lead and assigned to an
active team member. Completing a recurring task advances ``due_at`` /
``reminder_at`` to the next occurrence and reopens it (the row is the task
template); completing a one-off task closes it with ``completed_at``. Every
mutation is mirrored into the activity trail (TASK_CREATED / TASK_UPDATED /
TASK_COMPLETED / TASK_DELETED) so task history is auditable.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, RecurrenceFrequency, TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import User
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.lead import LeadRepository
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.services.base import commit_with_retry, utcnow

_OPEN_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS)


class TaskService:
    """Owns task business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tasks = TaskRepository(session)
        self._leads = LeadRepository(session)
        self._users = UserRepository(session)
        self._activity = ActivityLogRepository(session)

    # -- reads ----------------------------------------------------------

    async def get(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> Task:
        return await self._tasks.get_or_404(organization_id, task_id)

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
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        return await self._tasks.list_tasks(
            organization_id,
            lead_id=lead_id,
            assignee_user_id=assignee_user_id,
            status=status,
            priority=priority,
            due_before=due_before,
            due_after=due_after,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )

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
        return await self._tasks.count(
            organization_id,
            lead_id=lead_id,
            assignee_user_id=assignee_user_id,
            status=status,
            priority=priority,
            due_before=due_before,
            due_after=due_after,
        )

    async def due_reminders(
        self, organization_id: uuid.UUID, *, before: datetime | None = None
    ) -> list[Task]:
        """Return open tasks whose reminder time has arrived."""
        return await self._tasks.list_due_for_reminder(
            organization_id, before=before or utcnow()
        )

    # -- mutations ------------------------------------------------------

    async def create(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        title: str,
        description: str | None = None,
        lead_id: uuid.UUID | None = None,
        assignee_user_id: uuid.UUID | None = None,
        due_at: datetime | None = None,
        reminder_at: datetime | None = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        recurrence_frequency: RecurrenceFrequency | None = None,
        recurrence_interval: int | None = None,
    ) -> Task:
        title = self._clean_title(title)
        if recurrence_frequency is not None:
            recurrence_interval = recurrence_interval or 1
        await self._validate_links(
            organization_id,
            lead_id=lead_id,
            assignee_user_id=assignee_user_id,
        )
        self._validate_schedule(due_at, reminder_at)
        self._validate_recurrence(recurrence_frequency, recurrence_interval)
        task = Task(
            organization_id=organization_id,
            lead_id=lead_id,
            assignee_user_id=assignee_user_id,
            created_by_user_id=actor.id,
            title=title,
            description=description,
            status=TaskStatus.TODO,
            priority=priority,
            due_at=due_at,
            reminder_at=reminder_at,
            recurrence_frequency=recurrence_frequency,
            recurrence_interval=recurrence_interval,
        )
        self._tasks.add(task)
        self._activity.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id,
                lead_id=lead_id,
                event_type=ActivityEventType.TASK_CREATED,
                entity_type="task",
                entity_id=task.id,
                description="Task created",
                metadata_={
                    "assignee_user_id": str(assignee_user_id) if assignee_user_id else None,
                    "due_at": due_at.isoformat() if due_at else None,
                },
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return task

    async def update(
        self,
        organization_id: uuid.UUID,
        actor: User,
        task_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        lead_id: uuid.UUID | None = None,
        assignee_user_id: uuid.UUID | None = None,
        due_at: datetime | None = None,
        reminder_at: datetime | None = None,
        priority: TaskPriority | None = None,
        status: TaskStatus | None = None,
        recurrence_frequency: RecurrenceFrequency | None = None,
        recurrence_interval: int | None = None,
    ) -> Task:
        """Partial update; a requested ``completed`` status routes to completion."""
        task = await self._tasks.get_or_404(organization_id, task_id)

        changed = False
        if title is not None:
            task.title = self._clean_title(title)
            changed = True
        if description is not None:
            task.description = description
            changed = True
        if lead_id is not None:
            await self._validate_links(organization_id, lead_id=lead_id)
            if task.lead_id != lead_id:
                task.lead_id = lead_id
                changed = True
        if assignee_user_id is not None:
            await self._validate_links(
                organization_id, assignee_user_id=assignee_user_id
            )
            if task.assignee_user_id != assignee_user_id:
                task.assignee_user_id = assignee_user_id
                changed = True
        if due_at is not None:
            task.due_at = due_at
            changed = True
        if reminder_at is not None:
            task.reminder_at = reminder_at
            changed = True
        if priority is not None and task.priority is not priority:
            task.priority = priority
            changed = True
        if recurrence_frequency is not None:
            task.recurrence_frequency = recurrence_frequency
            task.recurrence_interval = recurrence_interval or 1
            changed = True
        if recurrence_interval is not None:
            if task.recurrence_frequency is None:
                raise AppError(
                    code="task.recurrence_requires_frequency",
                    message="A recurrence interval requires a recurrence frequency",
                    status_code=400,
                )
            task.recurrence_interval = recurrence_interval
            changed = True
        self._validate_schedule(task.due_at, task.reminder_at)
        if status is TaskStatus.COMPLETED:
            return await self._finalize_completion(organization_id, actor, task)
        if status is not None and task.status is not status:
            task.status = status
            changed = True
        if task.status in _OPEN_STATUSES and task.completed_at is not None:
            task.completed_at = None

        if changed:
            self._activity.add(
                ActivityLog(
                    organization_id=organization_id,
                    user_id=actor.id,
                    lead_id=task.lead_id,
                    event_type=ActivityEventType.TASK_UPDATED,
                    entity_type="task",
                    entity_id=task.id,
                    description="Task updated",
                    metadata_={"status": task.status.value},
                    occurred_at=utcnow(),
                )
            )
        await commit_with_retry(self._session)
        return task

    async def complete(
        self,
        organization_id: uuid.UUID,
        actor: User,
        task_id: uuid.UUID,
    ) -> Task:
        """Mark a task done; recurring tasks advance to the next occurrence."""
        task = await self._tasks.get_or_404(organization_id, task_id)
        return await self._finalize_completion(organization_id, actor, task)

    async def _finalize_completion(
        self, organization_id: uuid.UUID, actor: User, task: Task
    ) -> Task:
        if task.status is TaskStatus.COMPLETED:
            return task
        recurred = self._advance_recurrence(task)
        if recurred:
            task.status = TaskStatus.TODO
            task.completed_at = None
        else:
            task.status = TaskStatus.COMPLETED
            task.completed_at = utcnow()
        self._activity.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id,
                lead_id=task.lead_id,
                event_type=ActivityEventType.TASK_COMPLETED,
                entity_type="task",
                entity_id=task.id,
                description=(
                    "Recurring task occurrence completed"
                    if recurred
                    else "Task completed"
                ),
                metadata_={"recurred": recurred},
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return task

    async def delete(
        self, organization_id: uuid.UUID, actor: User, task_id: uuid.UUID
    ) -> None:
        task = await self._tasks.get_or_404(organization_id, task_id)
        await self._tasks.delete(task)
        self._activity.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id,
                lead_id=task.lead_id,
                event_type=ActivityEventType.TASK_DELETED,
                entity_type="task",
                entity_id=task.id,
                description="Task deleted",
                metadata_={"title": task.title},
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _clean_title(title: str) -> str:
        cleaned = title.strip()
        if not cleaned:
            raise AppError(
                code="task.title_required",
                message="Task title is required",
                status_code=400,
            )
        return cleaned

    async def _validate_links(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID | None = None,
        assignee_user_id: uuid.UUID | None = None,
    ) -> None:
        if lead_id is not None:
            await self._leads.get_or_404(organization_id, lead_id)
        if assignee_user_id is not None:
            assignee = await self._users.get_or_404(
                organization_id, assignee_user_id
            )
            if not assignee.is_active:
                raise AppError(
                    code="task.invalid_assignee",
                    message="Assignee is not an active team member",
                    status_code=400,
                )

    @staticmethod
    def _validate_schedule(due_at: datetime | None, reminder_at: datetime | None) -> None:
        if due_at is not None and reminder_at is not None and reminder_at > due_at:
            raise AppError(
                code="task.reminder_after_due",
                message="Reminder time cannot be after the due date",
                status_code=400,
            )

    @staticmethod
    def _validate_recurrence(
        frequency: RecurrenceFrequency | None, interval: int | None
    ) -> None:
        if frequency is None and interval is not None:
            raise AppError(
                code="task.recurrence_requires_frequency",
                message="A recurrence interval requires a recurrence frequency",
                status_code=400,
            )

    @staticmethod
    def _advance_recurrence(task: Task) -> bool:
        """Advance a recurring task's schedule; returns whether it recurred."""
        if task.recurrence_frequency is None or task.recurrence_interval is None:
            return False
        interval = task.recurrence_interval
        if task.due_at is not None:
            task.due_at = TaskService._advance_time(
                task.due_at, task.recurrence_frequency, interval
            )
        if task.reminder_at is not None:
            task.reminder_at = TaskService._advance_time(
                task.reminder_at, task.recurrence_frequency, interval
            )
        return True

    @staticmethod
    def _advance_time(
        when: datetime, frequency: RecurrenceFrequency, interval: int
    ) -> datetime:
        """Shift a timestamp by ``interval`` of ``frequency`` (calendar-aware)."""
        if frequency is RecurrenceFrequency.DAILY:
            return when + timedelta(days=interval)
        if frequency is RecurrenceFrequency.WEEKLY:
            return when + timedelta(weeks=interval)
        month = when.month - 1 + interval
        year = when.year + month // 12
        month = month % 12 + 1
        day = min(when.day, calendar.monthrange(year, month)[1])
        return when.replace(year=year, month=month, day=day)
