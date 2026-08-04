"""WorkflowEvent endpoints: list, publish."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.workflow_event import (
    WorkflowEventCreate,
    WorkflowEventListResponse,
    WorkflowEventPublish,
    WorkflowEventRead,
)
from app.services.workflow_event_service import WorkflowEventService

if TYPE_CHECKING:
    pass

router = APIRouter()

_read = Depends(require_permission(Permission.WORKFLOW_READ))
_write = Depends(require_permission(Permission.WORKFLOW_WRITE))


@router.get(
    "",
    response_model=WorkflowEventListResponse,
    summary="List workflow events",
    dependencies=[_read],
)
async def list_events(
    db: DbSession,
    current_user: CurrentUser,
    event_type: str | None = None,
    consumed: bool | None = None,
    sort: str = Query(default="occurred_at", pattern="^(occurred_at|event_type|consumed)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> WorkflowEventListResponse:
    service = WorkflowEventService(db)
    events = await service.list_events(
        current_user.organization_id,
        event_type=event_type,
        consumed=consumed,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    total = await service.count_events(
        current_user.organization_id,
        event_type=event_type,
        consumed=consumed,
    )
    return WorkflowEventListResponse(
        items=[WorkflowEventRead.model_validate(e) for e in events],
        total=total,
    )


@router.post(
    "",
    response_model=WorkflowEventPublish,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a workflow event (triggers matching workflows)",
    dependencies=[_write],
)
async def publish_event(
    body: WorkflowEventCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowEventPublish:
    service = WorkflowEventService(db)
    event = await service.publish(
        body.model_copy(update={"organization_id": current_user.organization_id})
    )
    return WorkflowEventPublish(event_id=event.id, consumed=event.consumed)