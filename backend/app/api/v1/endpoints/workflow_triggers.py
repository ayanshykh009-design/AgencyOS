"""Workflow trigger endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.common import Page
from app.schemas.workflow_trigger import (
    WorkflowTriggerCreate,
    WorkflowTriggerRead,
    WorkflowTriggerUpdate,
)
from app.services.workflow_trigger_service import WorkflowTriggerService

router = APIRouter()

_read = Depends(require_permission(Permission.AUTOMATION_READ))
_write = Depends(require_permission(Permission.AUTOMATION_WRITE))
_manage = Depends(require_permission(Permission.AUTOMATION_MANAGE))


@router.post(
    "",
    response_model=WorkflowTriggerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a trigger",
    dependencies=[_write],
)
async def create_trigger(
    body: WorkflowTriggerCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowTriggerRead:
    """Create a trigger for a workflow."""
    service = WorkflowTriggerService(db)
    trigger = await service.create(
        body.model_copy(update={"organization_id": current_user.organization_id})
    )
    return WorkflowTriggerRead.model_validate(trigger)


@router.get(
    "",
    response_model=Page[WorkflowTriggerRead],
    summary="List triggers",
    dependencies=[_read],
)
async def list_triggers(
    db: DbSession,
    current_user: CurrentUser,
    workflow_id: uuid.UUID | None = Query(default=None),
    trigger_type: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[WorkflowTriggerRead]:
    """List triggers with optional filters."""
    service = WorkflowTriggerService(db)
    triggers = await service.list_triggers(
        current_user.organization_id,
        workflow_id=workflow_id,
        trigger_type=trigger_type,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )
    total = await service.count_triggers(
        current_user.organization_id,
        workflow_id=workflow_id,
        trigger_type=trigger_type,
        enabled=enabled,
    )
    return Page(
        items=[WorkflowTriggerRead.model_validate(t) for t in triggers],
        total=total,
    )


@router.get(
    "/{trigger_id}",
    response_model=WorkflowTriggerRead,
    summary="Get a trigger",
    dependencies=[_read],
)
async def get_trigger(
    trigger_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowTriggerRead:
    """Return a single trigger."""
    service = WorkflowTriggerService(db)
    trigger = await service.get_trigger(current_user.organization_id, trigger_id)
    return WorkflowTriggerRead.model_validate(trigger)


@router.patch(
    "/{trigger_id}",
    response_model=WorkflowTriggerRead,
    summary="Update a trigger",
    dependencies=[_write],
)
async def update_trigger(
    trigger_id: uuid.UUID,
    body: WorkflowTriggerUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowTriggerRead:
    """Partially update a trigger."""
    service = WorkflowTriggerService(db)
    trigger = await service.update(
        current_user.organization_id,
        trigger_id,
        body,
    )
    return WorkflowTriggerRead.model_validate(trigger)


@router.post(
    "/{trigger_id}/enable",
    response_model=WorkflowTriggerRead,
    summary="Enable a trigger",
    dependencies=[_write],
)
async def enable_trigger(
    trigger_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowTriggerRead:
    """Enable a trigger."""
    service = WorkflowTriggerService(db)
    trigger = await service.enable(current_user.organization_id, trigger_id)
    return WorkflowTriggerRead.model_validate(trigger)


@router.post(
    "/{trigger_id}/disable",
    response_model=WorkflowTriggerRead,
    summary="Disable a trigger",
    dependencies=[_write],
)
async def disable_trigger(
    trigger_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowTriggerRead:
    """Disable a trigger."""
    service = WorkflowTriggerService(db)
    trigger = await service.disable(current_user.organization_id, trigger_id)
    return WorkflowTriggerRead.model_validate(trigger)


@router.delete(
    "/{trigger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trigger",
    dependencies=[_manage],
)
async def delete_trigger(
    trigger_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a trigger."""
    service = WorkflowTriggerService(db)
    await service.delete(current_user.organization_id, trigger_id)