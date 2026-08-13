"""Founder endpoints: generated briefings + business insights."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import BriefingType, InsightSeverity, InsightStatus
from app.schemas.briefing import (
    BriefingCreate,
    BriefingListResponse,
    BriefingRead,
)
from app.schemas.business_insight import (
    BusinessInsightCounts,
    BusinessInsightCreate,
    BusinessInsightListResponse,
    BusinessInsightRead,
    BusinessInsightUpdate,
)
from app.services.founder_service import FounderService

router = APIRouter()

_read = Depends(require_permission(Permission.GROWTH_READ))
_manage = Depends(require_permission(Permission.GROWTH_MANAGE))

_metadata_key = "metadata"


def _extract_metadata(data: dict) -> dict:
    meta = data.pop(_metadata_key, None)
    return meta or {}


# -- briefings -------------------------------------------------------


@router.get(
    "/briefings",
    response_model=BriefingListResponse,
    summary="List founder briefings (optional type filter)",
    dependencies=[_read],
)
async def list_briefings(
    db: DbSession,
    current_user: CurrentUser,
    briefing_type: BriefingType | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> BriefingListResponse:
    service = FounderService(db)
    items = await service.list_briefings(
        current_user.organization_id,
        briefing_type=briefing_type,
        limit=limit,
        offset=offset,
    )
    return BriefingListResponse(
        items=[BriefingRead.model_validate(b) for b in items], total=len(items)
    )


@router.get(
    "/briefings/latest",
    response_model=BriefingRead,
    summary="Most recent briefing of a given cadence",
    dependencies=[_read],
)
async def latest_briefing(
    db: DbSession,
    current_user: CurrentUser,
    briefing_type: BriefingType = Query(default=BriefingType.DAILY),
) -> BriefingRead:
    service = FounderService(db)
    briefing = await service.latest_briefing(current_user.organization_id, briefing_type)
    return BriefingRead.model_validate(briefing)


@router.post(
    "/briefings",
    response_model=BriefingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a founder briefing",
    dependencies=[_manage],
)
async def create_briefing(
    body: BriefingCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> BriefingRead:
    service = FounderService(db)
    data = body.model_dump(exclude={"organization_id"})
    metadata = _extract_metadata(data)
    briefing = await service.create_briefing(
        current_user.organization_id, metadata_=metadata, **data
    )
    return BriefingRead.model_validate(briefing)


@router.get(
    "/briefings/{briefing_id}",
    response_model=BriefingRead,
    summary="Get a briefing",
    dependencies=[_read],
)
async def get_briefing(
    briefing_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> BriefingRead:
    service = FounderService(db)
    briefing = await service.get_briefing(current_user.organization_id, briefing_id)
    return BriefingRead.model_validate(briefing)


# -- insights --------------------------------------------------------


@router.get(
    "/insights",
    response_model=BusinessInsightListResponse,
    summary="List business insights (optional status/severity filter)",
    dependencies=[_read],
)
async def list_insights(
    db: DbSession,
    current_user: CurrentUser,
    status: InsightStatus | None = None,
    severity: InsightSeverity | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> BusinessInsightListResponse:
    service = FounderService(db)
    items = await service.list_insights(
        current_user.organization_id,
        status=status,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return BusinessInsightListResponse(
        items=[BusinessInsightRead.model_validate(i) for i in items], total=len(items)
    )


@router.get(
    "/insights/counts",
    response_model=BusinessInsightCounts,
    summary="Active insight count + counts by type",
    dependencies=[_read],
)
async def insight_counts(db: DbSession, current_user: CurrentUser) -> BusinessInsightCounts:
    service = FounderService(db)
    open_count, by_type = await service.insight_counts(current_user.organization_id)
    return BusinessInsightCounts(open=open_count, by_type=by_type)


@router.get(
    "/insights/{insight_id}",
    response_model=BusinessInsightRead,
    summary="Get a business insight",
    dependencies=[_read],
)
async def get_insight(
    insight_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> BusinessInsightRead:
    service = FounderService(db)
    insight = await service.get_insight(current_user.organization_id, insight_id)
    return BusinessInsightRead.model_validate(insight)


@router.patch(
    "/insights/{insight_id}",
    response_model=BusinessInsightRead,
    summary="Update an insight (triage status/severity)",
    dependencies=[_manage],
)
async def update_insight(
    insight_id: uuid.UUID,
    body: BusinessInsightUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> BusinessInsightRead:
    service = FounderService(db)
    data = body.model_dump(exclude_unset=True)
    insight = await service.update_insight(current_user.organization_id, insight_id, **data)
    return BusinessInsightRead.model_validate(insight)


@router.delete(
    "/insights/{insight_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a business insight",
    dependencies=[_manage],
)
async def delete_insight(insight_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    service = FounderService(db)
    await service.delete_insight(current_user.organization_id, insight_id)


@router.post(
    "/insights",
    response_model=BusinessInsightRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a business insight",
    dependencies=[_manage],
)
async def create_insight(
    body: BusinessInsightCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> BusinessInsightRead:
    service = FounderService(db)
    data = body.model_dump(exclude={"organization_id"})
    metadata = _extract_metadata(data)
    insight = await service.create_insight(current_user.organization_id, metadata_=metadata, **data)
    return BusinessInsightRead.model_validate(insight)
