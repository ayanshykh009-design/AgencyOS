"""Research endpoints: trigger/enrich research for a lead, get research status/result."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.schemas.lead_research import LeadResearchRead, LeadResearchUpdate
from app.services.research_service import ResearchService
from app.workers.research_worker import ResearchWorker

router = APIRouter()


@router.post(
    "/{lead_id}",
    response_model=LeadResearchRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger AI research for a lead",
)
async def trigger_research(
    lead_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
    force_refresh: bool = Query(default=False, description="Re-run research even if completed"),
) -> LeadResearchRead:
    """Enqueue AI enrichment for a lead. Returns the research row (status: in_progress)."""
    service = ResearchService(db)
    # Start the research synchronously to get the in_progress row, then background the rest
    research = await service.run(
        lead_id=lead_id,
        organization_id=current_user.organization_id,
        force_refresh=force_refresh,
    )
    # If still in_progress, also queue the worker (for long-running enrichment)
    if research.status == "in_progress":
        background_tasks.add_task(
            ResearchWorker.process_job,
            lead_id,
            current_user.organization_id,
            force_refresh=force_refresh,
        )
    return LeadResearchRead.model_validate(research)


@router.get(
    "/{lead_id}",
    response_model=LeadResearchRead,
    summary="Get research for a lead",
)
async def get_research(
    lead_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> LeadResearchRead:
    """Return the latest research row for the lead."""
    service = ResearchService(db)
    research = await service.get_or_404(
        lead_id=lead_id, organization_id=current_user.organization_id
    )
    return LeadResearchRead.model_validate(research)


@router.patch(
    "/{lead_id}",
    response_model=LeadResearchRead,
    summary="Update research fields (manual override)",
)
async def update_research(
    lead_id: uuid.UUID,
    body: LeadResearchUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> LeadResearchRead:
    """Partially update research (e.g., manual corrections)."""
    service = ResearchService(db)
    research = await service.get_or_404(
        lead_id=lead_id, organization_id=current_user.organization_id
    )

    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "status" and value not in ("pending", "in_progress", "completed", "failed"):
            raise AppError(
                code="research.invalid_status", message="invalid research status", status_code=400
            )
        setattr(research, field, value)

    await db.commit()
    await db.refresh(research)
    return LeadResearchRead.model_validate(research)


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete research for a lead (reverts to pending)",
)
async def delete_research(
    lead_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete the research row; next trigger will re-create it."""
    service = ResearchService(db)
    await service.delete(lead_id=lead_id, organization_id=current_user.organization_id)
