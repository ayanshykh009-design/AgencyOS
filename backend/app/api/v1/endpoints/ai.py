"""AI automation endpoints: tool manifest, brain run, and n8n dispatch.

NOTE: intentionally does NOT use ``from __future__ import annotations``.
slowapi's ``functools.wraps`` copies string annotations and FastAPI then
resolves them against slowapi's globals, producing unresolved ForwardRefs.
"""
from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.schemas.ai import (
    BrainRunRequest,
    BrainRunResponse,
    DispatchRequest,
    DispatchResponse,
    ToolCallRead,
    ToolManifestEntry,
    ToolResultRead,
)
from app.schemas.organization import (
    OrganizationAISettingsRead,
    OrganizationAISettingsUpdate,
)
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
    provider, model, overridden = await service.get_ai_settings(current_user.organization_id)
    return OrganizationAISettingsRead(provider=provider, model=model, overridden=overridden)


@router.patch(
    "/settings",
    response_model=OrganizationAISettingsRead,
    summary="Update the organization's AI defaults",
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def update_ai_settings(
    request: Request,
    body: OrganizationAISettingsUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> OrganizationAISettingsRead:
    """Set per-org LLM provider/model; falls back to env when unset."""
    service = AIService(db)
    await service.update_ai_settings(
        current_user.organization_id,
        provider=body.provider,
        model=body.model,
    )
    provider, model, overridden = await service.get_ai_settings(current_user.organization_id)
    return OrganizationAISettingsRead(provider=provider, model=model, overridden=overridden)


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
    response_model=BrainRunResponse,
    summary="Run the AI brain for a goal on a lead",
)
@limiter.limit(settings.RATE_LIMIT_AI)
async def run_brain(
    request: Request,
    body: BrainRunRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> BrainRunResponse:
    """Execute the brain to draft outreach, research, or dispatch via n8n."""
    service = AIService(db)
    result = await service.run(
        goal=body.goal,
        lead_id=body.lead_id,
        organization_id=current_user.organization_id,
        channel=body.channel,
        recent_messages=body.recent_messages,
    )
    return BrainRunResponse(
        success=result.success,
        response=result.response,
        error=result.error,
        steps_taken=result.steps_taken,
        tool_calls=[
            ToolCallRead(name=tc.name, arguments=tc.arguments or {}) for tc in result.tool_calls
        ],
        tool_results=[
            ToolResultRead(ok=tr.ok, error=tr.error, text=tr.text) for tr in result.tool_results
        ],
    )


@router.post(
    "/dispatch",
    response_model=DispatchResponse,
    summary="Dispatch a draft to the n8n automation platform",
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
