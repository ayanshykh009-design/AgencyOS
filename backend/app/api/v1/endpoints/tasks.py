"""Task endpoints: CRUD, completion, recurrence, and due-reminder sweep."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import TaskPriority, TaskStatus
from app.schemas.common import Page
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter()

_read = Depends(require_permission(Permission.TASK_READ))
_write = Depends(require_permission(Permission.TASK_WRITE))
_manage = Depends(require_permission(Permission.TASK_MANAGE))


@router.get(
    "",
    response_model=Page[TaskRead],
    summary="List tasks with filters",
    dependencies=[_read],
)
async def list_tasks(
    db: DbSession,
    current_user: CurrentUser,
    lead_id: uuid.UUID | None = None,
    assignee_user_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    sort: str = Query(default="due_at", pattern="^(due_at|created_at|priority|title)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[TaskRead]:
    service = TaskService(db)
    tasks = await service.list_tasks(
        current_user.organization_id,
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
    total = await service.count(
        current_user.organization_id,
        lead_id=lead_id,
        assignee_user_id=assignee_user_id,
        status=status,
        priority=priority,
        due_before=due_before,
        due_after=due_after,
    )
    return Page(
        items=[TaskRead.model_validate(t) for t in tasks],
        total=total,
    )


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    dependencies=[_write],
)
async def create_task(
    body: TaskCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> TaskRead:
    service = TaskService(db)
    task = await service.create(
        current_user.organization_id,
        current_user,
        title=body.title,
        description=body.description,
        lead_id=body.lead_id,
        assignee_user_id=body.assignee_user_id,
        due_at=body.due_at,
        reminder_at=body.reminder_at,
        priority=body.priority,
        recurrence_frequency=body.recurrence_frequency,
        recurrence_interval=body.recurrence_interval,
    )
    return TaskRead.model_validate(task)


@router.get(
    "/reminders/due",
    response_model=list[TaskRead],
    summary="List open tasks whose reminder time has arrived",
    dependencies=[_read],
)
async def due_reminders(
    db: DbSession,
    current_user: CurrentUser,
) -> list[TaskRead]:
    service = TaskService(db)
    tasks = await service.due_reminders(current_user.organization_id)
    return [TaskRead.model_validate(t) for t in tasks]


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    dependencies=[_read],
)
async def get_task(
    task_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> TaskRead:
    service = TaskService(db)
    task = await service.get(current_user.organization_id, task_id)
    return TaskRead.model_validate(task)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update a task (setting status to completed closes it)",
    dependencies=[_write],
)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> TaskRead:
    service = TaskService(db)
    task = await service.update(
        current_user.organization_id,
        current_user,
        task_id,
        title=body.title,
        description=body.description,
        lead_id=body.lead_id,
        assignee_user_id=body.assignee_user_id,
        due_at=body.due_at,
        reminder_at=body.reminder_at,
        priority=body.priority,
        status=body.status,
        recurrence_frequency=body.recurrence_frequency,
        recurrence_interval=body.recurrence_interval,
    )
    return TaskRead.model_validate(task)


@router.post(
    "/{task_id}/complete",
    response_model=TaskRead,
    summary="Complete a task (recurring tasks advance to the next occurrence)",
    dependencies=[_write],
)
async def complete_task(
    task_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> TaskRead:
    service = TaskService(db)
    task = await service.complete(
        current_user.organization_id, current_user, task_id
    )
    return TaskRead.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    dependencies=[_manage],
)
async def delete_task(
    task_id: uuid.UUID, db: DbSession, current_user: CurrentUser
):
    service = TaskService(db)
    await service.delete(current_user.organization_id, current_user, task_id)
