"""Workflow endpoints: CRUD, activation, and manual run."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import WorkflowStatus
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowRead,
    WorkflowUpdate,
)
from app.schemas.workflow_execution import (
    WorkflowExecutionListResponse,
    WorkflowExecutionRead,
)
from app.schemas.workflow_trigger import (
    WorkflowTriggerCreate,
    WorkflowTriggerListResponse,
    WorkflowTriggerRead,
    WorkflowTriggerUpdate,
)
from app.services.workflow_service import WorkflowService

if TYPE_CHECKING:
    pass

router = APIRouter()

_read = Depends(require_permission(Permission.WORKFLOW_READ))
_write = Depends(require_permission(Permission.WORKFLOW_WRITE))
_manage = Depends(require_permission(Permission.WORKFLOW_MANAGE))


# Workflow CRUD ---------------------------------------------------------------


@router.get(
    "",
    response_model=WorkflowListResponse,
    summary="List workflows with filters",
    dependencies=[_read],
)
async def list_workflows(
    db: DbSession,
    current_user: CurrentUser,
    status: WorkflowStatus | None = None,
    sort: str = Query(default="created_at", pattern="^(created_at|name|status|version)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> WorkflowListResponse:
    service = WorkflowService(db)
    workflows = await service.list_workflows(
        current_user.organization_id,
        status=status,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    total = await service.count_workflows(current_user.organization_id, status=status)
    return WorkflowListResponse(
        items=[WorkflowRead.model_validate(w) for w in workflows],
        total=total,
    )


@router.post(
    "",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workflow",
    dependencies=[_write],
)
async def create_workflow(
    body: WorkflowCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowRead:
    service = WorkflowService(db)
    workflow = await service.create(
        body.model_copy(update={"organization_id": current_user.organization_id}),
        created_by_user_id=current_user.id,
    )
    return WorkflowRead.model_validate(workflow)


@router.get(
    "/{workflow_id}",
    response_model=WorkflowRead,
    summary="Get a workflow",
    dependencies=[_read],
)
async def get_workflow(
    workflow_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowRead:
    service = WorkflowService(db)
    workflow = await service.get_or_404(current_user.organization_id, workflow_id)
    return WorkflowRead.model_validate(workflow)


@router.get(
    "/active",
    response_model=list[WorkflowRead],
    summary="List active workflows",
    dependencies=[_read],
)
async def list_active_workflows(
    db: DbSession,
    current_user: CurrentUser,
) -> list[WorkflowRead]:
    service = WorkflowService(db)
    workflows = await service.list_active(current_user.organization_id)
    return [WorkflowRead.model_validate(w) for w in workflows]


@router.patch(
    "/{workflow_id}",
    response_model=WorkflowRead,
    summary="Update a workflow",
    dependencies=[_write],
)
async def update_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowRead:
    service = WorkflowService(db)
    workflow = await service.update(
        current_user.organization_id,
        workflow_id,
        body,
        actor=current_user,
    )
    return WorkflowRead.model_validate(workflow)


@router.post(
    "/{workflow_id}/activate",
    response_model=WorkflowRead,
    summary="Activate a workflow (draft/paused -> active)",
    dependencies=[_manage],
)
async def activate_workflow(
    workflow_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowRead:
    service = WorkflowService(db)
    workflow = await service.activate(current_user.organization_id, workflow_id, actor=current_user)
    return WorkflowRead.model_validate(workflow)


@router.post(
    "/{workflow_id}/pause",
    response_model=WorkflowRead,
    summary="Pause an active workflow",
    dependencies=[_manage],
)
async def pause_workflow(
    workflow_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowRead:
    service = WorkflowService(db)
    workflow = await service.pause(current_user.organization_id, workflow_id, actor=current_user)
    return WorkflowRead.model_validate(workflow)


@router.post(
    "/{workflow_id}/archive",
    response_model=WorkflowRead,
    summary="Archive a workflow (terminal state)",
    dependencies=[_manage],
)
async def archive_workflow(
    workflow_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowRead:
    service = WorkflowService(db)
    workflow = await service.archive(current_user.organization_id, workflow_id, actor=current_user)
    return WorkflowRead.model_validate(workflow)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workflow",
    dependencies=[_manage],
)
async def delete_workflow(
    workflow_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    service = WorkflowService(db)
    await service.delete(current_user.organization_id, workflow_id, actor=current_user)


# Nested triggers -------------------------------------------------------------


@router.get(
    "/{workflow_id}/triggers",
    response_model=WorkflowTriggerListResponse,
    summary="List triggers for a workflow",
    dependencies=[_read],
)
async def list_triggers(
    workflow_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    trigger_type: str | None = None,
    enabled: bool | None = None,
    sort: str = Query(default="created_at", pattern="^(created_at|name|trigger_type)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> WorkflowTriggerListResponse:
    service = WorkflowService(db)
    triggers = await service.list_triggers(
        current_user.organization_id,
        workflow_id=workflow_id,
        trigger_type=trigger_type,
        enabled=enabled,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    total = await service.count_triggers(
        current_user.organization_id,
        workflow_id=workflow_id,
        trigger_type=trigger_type,
        enabled=enabled,
    )
    return WorkflowTriggerListResponse(
        items=[WorkflowTriggerRead.model_validate(t) for t in triggers],
        total=total,
    )


@router.post(
    "/{workflow_id}/triggers",
    response_model=WorkflowTriggerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a trigger for a workflow",
    dependencies=[_write],
)
async def create_trigger(
    workflow_id: uuid.UUID,
    body: WorkflowTriggerCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowTriggerRead:
    if body.workflow_id != workflow_id:
        from app.core.errors import AppError

        raise AppError(
            code="workflow_trigger.workflow_id_mismatch",
            message="workflow_id in body must match path parameter",
            status_code=400,
        )
    service = WorkflowService(db)
    trigger = await service.create_trigger(
        current_user.organization_id,
        body.model_copy(update={"organization_id": current_user.organization_id}),
    )
    return WorkflowTriggerRead.model_validate(trigger)


@router.patch(
    "/{workflow_id}/triggers/{trigger_id}",
    response_model=WorkflowTriggerRead,
    summary="Update a trigger",
    dependencies=[_write],
)
async def update_trigger(
    workflow_id: uuid.UUID,
    trigger_id: uuid.UUID,
    body: WorkflowTriggerUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowTriggerRead:
    service = WorkflowService(db)
    trigger = await service.update_trigger(
        current_user.organization_id,
        trigger_id,
        body,
    )
    return WorkflowTriggerRead.model_validate(trigger)


@router.delete(
    "/{workflow_id}/triggers/{trigger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trigger",
    dependencies=[_manage],
)
async def delete_trigger(
    workflow_id: uuid.UUID,
    trigger_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    service = WorkflowService(db)
    await service.delete_trigger(current_user.organization_id, trigger_id)


# Nested executions -----------------------------------------------------------


@router.get(
    "/{workflow_id}/executions",
    response_model=WorkflowExecutionListResponse,
    summary="List executions for a workflow",
    dependencies=[_read],
)
async def list_workflow_executions(
    workflow_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    status: str | None = None,
    sort: str = Query(default="created_at", pattern="^(created_at|started_at|finished_at|status)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> WorkflowExecutionListResponse:
    from app.models.enums import ExecutionStatus

    exec_status = ExecutionStatus(status) if status else None
    # Use the execution service for listing
    from app.services.workflow_execution_service import WorkflowExecutionService

    exec_service = WorkflowExecutionService(db)
    executions = await exec_service.list_executions(
        current_user.organization_id,
        workflow_id=workflow_id,
        status=exec_status,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    total = await exec_service.count_executions(
        current_user.organization_id,
        workflow_id=workflow_id,
        status=exec_status,
    )
    return WorkflowExecutionListResponse(
        items=[WorkflowExecutionRead.model_validate(e) for e in executions],
        total=total,
    )
