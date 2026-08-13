"""Agent endpoints: run records (read/create/update/cancel) + agent state.

NOTE: intentionally does NOT use ``from __future__ import annotations``;
slowapi's ``@limiter.limit`` wrapper breaks FastAPI's forward-ref resolution.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import limiter
from app.models.enums import AgentRunStatus, AgentStateStatus
from app.schemas.agent_run import AgentRunCreate, AgentRunListResponse, AgentRunRead, AgentRunUpdate
from app.schemas.agent_state import AgentStateListResponse, AgentStateRead, AgentStateUpsert
from app.services.agent_service import AgentService

router = APIRouter()

_read = Depends(require_permission(Permission.AGENT_READ))
_manage = Depends(require_permission(Permission.AGENT_MANAGE))


@router.get(
    "/states",
    response_model=AgentStateListResponse,
    summary="List per-agent health states",
    dependencies=[_read],
)
async def list_agent_states(
    db: DbSession,
    current_user: CurrentUser,
    status: AgentStateStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> AgentStateListResponse:
    service = AgentService(db)
    states = await service.list_states(current_user.organization_id, status=status, limit=limit)
    return AgentStateListResponse(
        items=[AgentStateRead.model_validate(s) for s in states], total=len(states)
    )


@router.patch(
    "/states/{agent_name}",
    response_model=AgentStateRead,
    summary="Upsert an agent health state",
    dependencies=[_manage],
)
async def upsert_agent_state(
    agent_name: str,
    body: AgentStateUpsert,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentStateRead:
    service = AgentService(db)
    data = body.model_dump()
    agent_name_payload = data.pop("agent_name")
    if agent_name_payload != agent_name:
        from app.core.errors import AppError

        raise AppError(
            code="agent.name_mismatch",
            message="Path agent_name does not match body",
            status_code=400,
        )
    state = await service.upsert_state(current_user.organization_id, agent_name=agent_name, **data)
    return AgentStateRead.model_validate(state)


@router.get(
    "/runs",
    response_model=AgentRunListResponse,
    summary="List agent run records",
    dependencies=[_read],
)
async def list_agent_runs(
    db: DbSession,
    current_user: CurrentUser,
    agent_name: str | None = Query(default=None, max_length=200),
    status: AgentRunStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AgentRunListResponse:
    service = AgentService(db)
    runs = await service.list_runs(
        current_user.organization_id,
        agent_name=agent_name,
        status=status,
        limit=limit,
        offset=offset,
    )
    return AgentRunListResponse(
        items=[AgentRunRead.model_validate(r) for r in runs], total=len(runs)
    )


@router.post(
    "/runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent run record (queued, not executed)",
    dependencies=[_manage],
)
@limiter.limit(settings.RATE_LIMIT_AI)
async def create_agent_run(
    request: Request,
    body: AgentRunCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentRunRead:
    service = AgentService(db)
    data = body.model_dump(exclude={"organization_id"})
    run = await service.create_run(
        current_user.organization_id,
        agent_name=data["agent_name"],
        status=data["status"],
        trigger=data["trigger"],
        workflow_id=data["workflow_id"],
        input_=data["input"],
        idempotency_key=data["idempotency_key"],
    )
    return AgentRunRead.model_validate(run)


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunRead,
    summary="Get an agent run record",
    dependencies=[_read],
)
async def get_agent_run(
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentRunRead:
    service = AgentService(db)
    run = await service.get_run(current_user.organization_id, run_id)
    return AgentRunRead.model_validate(run)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=AgentRunRead,
    summary="Cancel an agent run",
    dependencies=[_manage],
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def cancel_agent_run(
    request: Request,
    run_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentRunRead:
    service = AgentService(db)
    run = await service.cancel_run(
        current_user.organization_id,
        run_id,
        cancelled_by_user_id=current_user.id,
    )
    return AgentRunRead.model_validate(run)


@router.patch(
    "/runs/{run_id}",
    response_model=AgentRunRead,
    summary="Update agent run metadata (status is runtime-owned)",
    dependencies=[_manage],
)
async def update_agent_run(
    run_id: uuid.UUID,
    body: AgentRunUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentRunRead:
    service = AgentService(db)
    data = body.model_dump(exclude_unset=True)
    run = await service.update_run(current_user.organization_id, run_id, **data)
    return AgentRunRead.model_validate(run)
