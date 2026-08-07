"""WorkflowExecution endpoints: queue, list, get, start, retry, cancel."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, has_permission, require_permission
from app.models.enums import ExecutionStatus
from app.schemas.execution_event import ExecutionEventListResponse, ExecutionEventRead
from app.schemas.workflow_execution import (
    WorkflowExecutionCreate,
    WorkflowExecutionListResponse,
    WorkflowExecutionQueue,
    WorkflowExecutionRead,
)
from app.services.execution_event_service import ExecutionEventService
from app.services.workflow_execution_service import WorkflowExecutionService

if TYPE_CHECKING:
    pass

router = APIRouter()

_read = Depends(require_permission(Permission.EXECUTION_READ))
_write = Depends(require_permission(Permission.WORKFLOW_WRITE))


@router.post(
    "",
    response_model=WorkflowExecutionQueue,
    status_code=status.HTTP_201_CREATED,
    summary="Queue a workflow execution",
    dependencies=[_write],
)
async def queue_execution(
    body: WorkflowExecutionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowExecutionQueue:
    service = WorkflowExecutionService(db)
    execution = await service.queue(
        body.model_copy(update={"organization_id": current_user.organization_id}),
        requested_by_user_id=current_user.id,
        bypass_pending_cap=has_permission(current_user.role, Permission.EXECUTION_MANAGE),
    )
    return WorkflowExecutionQueue(
        execution_id=execution.id,
        status=execution.status,
    )


@router.get(
    "",
    response_model=WorkflowExecutionListResponse,
    summary="List workflow executions with filters",
    dependencies=[_read],
)
async def list_executions(
    db: DbSession,
    current_user: CurrentUser,
    workflow_id: uuid.UUID | None = None,
    trigger_id: uuid.UUID | None = None,
    status: ExecutionStatus | None = None,
    sort: str = Query(default="created_at", pattern="^(created_at|started_at|finished_at|status)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> WorkflowExecutionListResponse:
    service = WorkflowExecutionService(db)
    executions = await service.list_executions(
        current_user.organization_id,
        workflow_id=workflow_id,
        trigger_id=trigger_id,
        status=status,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    total = await service.count_executions(
        current_user.organization_id,
        workflow_id=workflow_id,
        trigger_id=trigger_id,
        status=status,
    )
    return WorkflowExecutionListResponse(
        items=[WorkflowExecutionRead.model_validate(e) for e in executions],
        total=total,
    )


@router.get(
    "/{execution_id}",
    response_model=WorkflowExecutionRead,
    summary="Get a workflow execution",
    dependencies=[_read],
)
async def get_execution(
    execution_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowExecutionRead:
    service = WorkflowExecutionService(db)
    execution = await service.get_execution(current_user.organization_id, execution_id)
    return WorkflowExecutionRead.model_validate(execution)


@router.get(
    "/{execution_id}/events",
    response_model=ExecutionEventListResponse,
    summary="Get the technical timeline for a workflow execution",
    dependencies=[_read],
)
async def list_execution_events(
    execution_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ExecutionEventListResponse:
    service = ExecutionEventService(db)
    events = await service.list_by_execution(
        current_user.organization_id, execution_id, limit=limit, offset=offset
    )
    total = await service.count_by_execution(
        current_user.organization_id, execution_id
    )
    return ExecutionEventListResponse(
        items=[ExecutionEventRead.model_validate(e) for e in events],
        total=total,
    )


@router.post(
    "/{execution_id}/start",
    response_model=WorkflowExecutionRead,
    summary="Start a queued execution",
    dependencies=[_write],
)
async def start_execution(
    execution_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowExecutionRead:
    service = WorkflowExecutionService(db)
    execution = await service.start(
        current_user.organization_id,
        execution_id,
        actor_user_id=current_user.id,
    )
    return WorkflowExecutionRead.model_validate(execution)


@router.post(
    "/{execution_id}/retry",
    response_model=WorkflowExecutionRead,
    summary="Retry a failed or cancelled execution",
    dependencies=[_write],
)
async def retry_execution(
    execution_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowExecutionRead:
    service = WorkflowExecutionService(db)
    execution = await service.retry(
        current_user.organization_id,
        execution_id,
        actor_user_id=current_user.id,
    )
    return WorkflowExecutionRead.model_validate(execution)


@router.post(
    "/{execution_id}/complete",
    response_model=WorkflowExecutionRead,
    summary="Mark a running execution succeeded with an output payload",
    dependencies=[_write],
)
async def complete_execution(
    execution_id: uuid.UUID,
    body: dict,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowExecutionRead:
    service = WorkflowExecutionService(db)
    execution = await service.complete(
        current_user.organization_id,
        execution_id,
        output=body,
        actor_user_id=current_user.id,
    )
    return WorkflowExecutionRead.model_validate(execution)


@router.post(
    "/{execution_id}/fail",
    response_model=WorkflowExecutionRead,
    summary="Mark a running execution failed (optionally schedule a retry)",
    dependencies=[_write],
)
async def fail_execution(
    execution_id: uuid.UUID,
    body: dict,
    db: DbSession,
    current_user: CurrentUser,
    schedule_retry: bool = True,
) -> WorkflowExecutionRead:
    service = WorkflowExecutionService(db)
    execution = await service.fail(
        current_user.organization_id,
        execution_id,
        error=body,
        schedule_retry=schedule_retry,
        actor_user_id=current_user.id,
    )
    return WorkflowExecutionRead.model_validate(execution)


@router.post(
    "/{execution_id}/cancel",
    response_model=WorkflowExecutionRead,
    summary="Cancel a queued/running execution",
    dependencies=[_write],
)
async def cancel_execution(
    execution_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkflowExecutionRead:
    service = WorkflowExecutionService(db)
    execution = await service.cancel(
        current_user.organization_id,
        execution_id,
        cancelled_by_user_id=current_user.id,
    )
    return WorkflowExecutionRead.model_validate(execution)
