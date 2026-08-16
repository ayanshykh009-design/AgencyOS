"""AI automation endpoints: tool manifest, brain run, and n8n dispatch.

NOTE: intentionally does NOT use ``from __future__ import annotations``.
slowapi's ``functools.wraps`` copies string annotations and FastAPI then
resolves them against slowapi's globals, producing unresolved ForwardRefs.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.contextvars import request_id_var
from app.core.errors import AppError
from app.core.metrics import get_counter
from app.core.permissions import Permission, require_permission
from app.core.rate_limit import limiter
from app.models.enums import AgentRunStatus, AgentRunTrigger
from app.schemas.agent_run import AgentRunRead
from app.schemas.ai import (
    BrainRunRequest,
    DispatchRequest,
    DispatchResponse,
    ToolManifestEntry,
)
from app.schemas.organization import (
    OrganizationAISettingsRead,
    OrganizationAISettingsUpdate,
)
from app.services.agent_service import AgentService
from app.services.ai_service import AIService

router = APIRouter()


@router.get(
    "/settings",
    response_model=OrganizationAISettingsRead,
    summary="Get the organization's effective AI settings",
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_ai_settings(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> OrganizationAISettingsRead:
    """Return the resolved provider/model (per-org override else env defaults)."""
    service = AIService(db)
    provider, model, overridden, kill_switch = await service.get_ai_settings(
        current_user.organization_id
    )
    return OrganizationAISettingsRead(
        provider=provider, model=model, overridden=overridden, kill_switch=kill_switch
    )


@router.patch(
    "/settings",
    response_model=OrganizationAISettingsRead,
    summary="Update the organization's AI defaults",
    dependencies=[Depends(require_permission(Permission.AI_MANAGE))],
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def update_ai_settings(
    request: Request,
    body: OrganizationAISettingsUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> OrganizationAISettingsRead:
    """Set per-org LLM provider/model and AI kill switch; falls back to env."""
    service = AIService(db)
    await service.update_ai_settings(
        current_user.organization_id,
        provider=body.provider,
        model=body.model,
        kill_switch=body.kill_switch,
    )
    provider, model, overridden, kill_switch = await service.get_ai_settings(
        current_user.organization_id
    )
    return OrganizationAISettingsRead(
        provider=provider, model=model, overridden=overridden, kill_switch=kill_switch
    )


@router.get(
    "/tools",
    response_model=list[ToolManifestEntry],
    summary="List available AI tools",
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_tools(
    request: Request, db: DbSession, current_user: CurrentUser
) -> list[ToolManifestEntry]:
    """Return the static tool manifest (no LLM call)."""
    service = AIService(db)
    manifest = await service.tools()
    return [ToolManifestEntry.model_validate(entry) for entry in manifest]


@router.post(
    "/run",
    response_model=AgentRunRead,
    status_code=201,
    summary="Queue an AI brain run for a goal on a lead",
    dependencies=[Depends(require_permission(Permission.AI_RUN))],
)
@limiter.limit(settings.RATE_LIMIT_AI)
async def run_brain(
    request: Request,
    body: BrainRunRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> AgentRunRead:
    """Queue an AI run through the unified AgentRuntime lifecycle (M11-C).

    The run is created QUEUED (trigger ``ai_run``) and executed by the worker,
    so the response is an :class:`AgentRunRead` the client polls to completion.
    Tool authorization, the goal-scoped allow-list, and the per-org token/cost
    budget are enforced by the worker path; the HTTP layer only authorizes the
    request (``ai_run``) and persists the run.
    """
    service = AIService(db)
    # Per-org AI kill switch (F-SEC-3): fail fast before enqueuing a run.
    await service.assert_ai_enabled(current_user.organization_id)
    agent_name = service.agent_for_goal(body.goal)

    # Trace the run end-to-end from the originating request id.
    raw_trace = request_id_var.get()
    try:
        trace_id = UUID(raw_trace)
    except (ValueError, TypeError):
        trace_id = uuid4()

    run = await AgentService(db).create_run(
        current_user.organization_id,
        agent_name=agent_name,
        status=AgentRunStatus.QUEUED,
        trigger=AgentRunTrigger.AI_RUN,
        input_={
            "goal": body.goal,
            "lead_id": str(body.lead_id),
            "channel": body.channel,
            "recent_messages": body.recent_messages or [],
            "actor_user_id": str(current_user.id),
        },
        idempotency_key=body.idempotency_key,
        trace_id=trace_id,
    )
    get_counter(
        "ai_runs_total",
        description="AI (M11) runs queued via /api/v1/ai/run",
    ).add()
    return AgentRunRead.model_validate(run)


@router.post(
    "/dispatch",
    response_model=DispatchResponse,
    summary="Dispatch a draft to the n8n automation platform",
    dependencies=[Depends(require_permission(Permission.LEAD_WRITE))],
)
@limiter.limit(settings.RATE_LIMIT_AI)
async def dispatch(
    request: Request,
    body: DispatchRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> DispatchResponse:
    """Send a ready-to-send draft to the configured n8n workflow."""
    if not body.workflow.strip():
        raise AppError(code="ai.invalid_workflow", message="workflow is required", status_code=400)
    service = AIService(db)
    data = await service.dispatch(workflow=body.workflow, payload=body.payload)
    return DispatchResponse(workflow=body.workflow, status=200, data=data)
