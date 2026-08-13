"""Pipeline endpoints: stages, close reasons, Kanban board, stage moves."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import StageLifecycle
from app.schemas.lead import LeadRead
from app.schemas.pipeline import (
    CloseReasonCreate,
    CloseReasonRead,
    LeadStageMoveRequest,
    PipelineStageCreate,
    PipelineStageRead,
    PipelineStageUpdate,
    PipelineStageWithLeads,
    StageReorderRequest,
)
from app.services.lead_service import LeadService
from app.services.pipeline_service import PipelineService

router = APIRouter()

_admin = Depends(require_permission(Permission.PIPELINE_MANAGE))


@router.get(
    "/stages",
    response_model=list[PipelineStageRead],
    summary="List pipeline stages with lead counts",
)
async def list_stages(db: DbSession, current_user: CurrentUser) -> list[PipelineStageRead]:
    service = PipelineService(db)
    stages = await service.list_stages(current_user.organization_id)
    counts = await service.stage_counts(current_user.organization_id)
    reads = [PipelineStageRead.model_validate(s) for s in stages]
    for read in reads:
        read.lead_count = counts.get(read.id, 0)
    return reads


@router.post(
    "/stages",
    response_model=PipelineStageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pipeline stage",
    dependencies=[_admin],
)
async def create_stage(
    body: PipelineStageCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> PipelineStageRead:
    service = PipelineService(db)
    stage = await service.create_stage(
        current_user.organization_id,
        current_user,
        name=body.name,
        lifecycle=body.lifecycle,
        position=body.position,
    )
    return PipelineStageRead.model_validate(stage)


@router.patch(
    "/stages/{stage_id}",
    response_model=PipelineStageRead,
    summary="Rename or reorder a pipeline stage",
    dependencies=[_admin],
)
async def update_stage(
    stage_id: uuid.UUID,
    body: PipelineStageUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> PipelineStageRead:
    service = PipelineService(db)
    stage = await service.update_stage(
        current_user.organization_id,
        stage_id,
        name=body.name,
        position=body.position,
    )
    return PipelineStageRead.model_validate(stage)


@router.delete(
    "/stages/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a pipeline stage (leads move to an alternative)",
    dependencies=[_admin],
)
async def delete_stage(stage_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    service = PipelineService(db)
    await service.delete_stage(current_user.organization_id, stage_id)


@router.post(
    "/stages/reorder",
    response_model=list[PipelineStageRead],
    summary="Reorder pipeline stages",
    dependencies=[_admin],
)
async def reorder_stages(
    body: StageReorderRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> list[PipelineStageRead]:
    service = PipelineService(db)
    stages = await service.reorder_stages(current_user.organization_id, body.stage_ids)
    return [PipelineStageRead.model_validate(s) for s in stages]


@router.get(
    "/close-reasons",
    response_model=list[CloseReasonRead],
    summary="List close reasons (optionally filtered by lifecycle)",
)
async def list_close_reasons(
    db: DbSession,
    current_user: CurrentUser,
    lifecycle: StageLifecycle | None = None,
) -> list[CloseReasonRead]:
    service = PipelineService(db)
    reasons = await service.list_close_reasons(current_user.organization_id, lifecycle=lifecycle)
    return [CloseReasonRead.model_validate(r) for r in reasons]


@router.post(
    "/close-reasons",
    response_model=CloseReasonRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a close reason",
    dependencies=[_admin],
)
async def create_close_reason(
    body: CloseReasonCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> CloseReasonRead:
    service = PipelineService(db)
    reason = await service.create_close_reason(
        current_user.organization_id,
        current_user,
        name=body.name,
        lifecycle=body.lifecycle,
    )
    return CloseReasonRead.model_validate(reason)


@router.delete(
    "/close-reasons/{close_reason_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a close reason (blocked while in use)",
    dependencies=[_admin],
)
async def delete_close_reason(close_reason_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    service = PipelineService(db)
    await service.delete_close_reason(current_user.organization_id, close_reason_id)


@router.get(
    "/board",
    response_model=list[PipelineStageWithLeads],
    summary="Kanban board: stages with their lead cards",
)
async def board(
    db: DbSession,
    current_user: CurrentUser,
    limit_per_stage: int = Query(default=50, ge=1, le=200),
) -> list[PipelineStageWithLeads]:
    service = PipelineService(db)
    columns = await service.board(current_user.organization_id, limit_per_stage=limit_per_stage)
    result: list[PipelineStageWithLeads] = []
    for stage, leads in columns:
        read = PipelineStageRead.model_validate(stage)
        read.lead_count = len(leads)
        result.append(
            PipelineStageWithLeads(
                stage=read,
                leads=[LeadRead.model_validate(lead) for lead in leads],
            )
        )
    return result


@router.post(
    "/leads/{lead_id}/stage",
    response_model=LeadRead,
    summary="Move a lead onto a stage (closes it if the stage is won/lost)",
)
async def move_lead(
    lead_id: uuid.UUID,
    body: LeadStageMoveRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> LeadRead:
    lead = await LeadService(db).get(current_user.organization_id, lead_id)
    lead = await PipelineService(db).move(
        current_user.organization_id,
        current_user,
        lead,
        stage_id=body.stage_id,
        close_reason_id=body.close_reason_id,
    )
    return LeadRead.model_validate(lead)
