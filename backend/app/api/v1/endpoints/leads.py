"""Lead endpoints: CRUD, search, funnel, duplicate check."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models.enums import LeadStatus
from app.schemas.common import Page
from app.schemas.dashboard import DashboardLeadCounts
from app.schemas.lead import LeadCreate, LeadRead, LeadUpdate
from app.services.lead_service import LeadService

router = APIRouter()


@router.post(
    "",
    response_model=LeadRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lead",
)
async def create_lead(body: LeadCreate, db: DbSession, current_user: CurrentUser) -> LeadRead:
    """Create a lead (dedup keys are computed by PostgreSQL)."""
    service = LeadService(db)
    data = body.model_dump()
    data["organization_id"] = current_user.organization_id
    lead = await service.create(current_user.organization_id, data)
    return LeadRead.model_validate(lead)


@router.get(
    "",
    response_model=Page[LeadRead],
    summary="Search and filter leads",
)
async def list_leads(
    db: DbSession,
    current_user: CurrentUser,
    query: str | None = Query(default=None, max_length=255),
    status_filter: LeadStatus | None = Query(default=None, alias="status"),
    source_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    max_score: int | None = Query(default=None, ge=0, le=100),
    sort: str = Query(
        default="created_at",
        pattern="^(created_at|updated_at|score|first_name|company)$",
    ),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[LeadRead]:
    """Return a paginated, filtered lead list."""
    service = LeadService(db)
    leads, total = await service.search(
        current_user.organization_id,
        query=query,
        status=status_filter,
        source_id=source_id,
        owner_user_id=owner_user_id,
        min_score=min_score,
        max_score=max_score,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return Page(items=[LeadRead.model_validate(lead) for lead in leads], total=total)


@router.get(
    "/funnel",
    response_model=DashboardLeadCounts,
    summary="Lead counts by status",
)
async def lead_funnel(db: DbSession, current_user: CurrentUser) -> DashboardLeadCounts:
    """Return lead counts grouped by lifecycle status."""
    service = LeadService(db)
    counts = await service.funnel(current_user.organization_id)
    return DashboardLeadCounts.from_status_counts(counts, sum(counts.values()))


@router.get(
    "/duplicates",
    response_model=list[LeadRead],
    summary="Check for duplicate leads",
)
async def check_duplicates(
    db: DbSession,
    current_user: CurrentUser,
    email: str | None = Query(default=None, max_length=255),
    phone: str | None = Query(default=None, max_length=64),
    website: str | None = Query(default=None, max_length=255),
) -> list[LeadRead]:
    """Return existing leads matching any normalized contact key."""
    service = LeadService(db)
    duplicates = await service.duplicate_check(
        current_user.organization_id,
        email=email,
        phone=phone,
        website=website,
    )
    return [LeadRead.model_validate(lead) for lead in duplicates]


@router.get(
    "/{lead_id}",
    response_model=LeadRead,
    summary="Get a lead",
)
async def get_lead(lead_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> LeadRead:
    """Return a single lead."""
    service = LeadService(db)
    lead = await service.get(current_user.organization_id, lead_id)
    return LeadRead.model_validate(lead)


@router.patch(
    "/{lead_id}",
    response_model=LeadRead,
    summary="Update a lead",
)
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> LeadRead:
    """Partially update a lead."""
    service = LeadService(db)
    lead = await service.update(
        current_user.organization_id,
        lead_id,
        body.model_dump(exclude_unset=True),
    )
    return LeadRead.model_validate(lead)


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a lead",
)
async def delete_lead(lead_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    """Soft-delete a lead (kept for audit, excluded from queries)."""
    service = LeadService(db)
    await service.soft_delete(current_user.organization_id, lead_id)
