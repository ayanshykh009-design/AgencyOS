"""Provider usage endpoints: recording + totals (no credentials exposed)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, require_role
from app.models.enums import UserRole
from app.schemas.provider import ProviderUsageCreate, ProviderUsageRead
from app.services.provider_usage_service import ProviderUsageService

router = APIRouter()

_admin_only = require_role(UserRole.OWNER, UserRole.ADMIN)


@router.get(
    "",
    response_model=list[ProviderUsageRead],
    summary="List provider usage records",
)
async def list_usage(
    db: DbSession,
    current_user: CurrentUser,
    provider: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ProviderUsageRead]:
    service = ProviderUsageService(db)
    records = await service.list(
        current_user.organization_id,
        provider=provider,
        limit=limit,
        offset=offset,
    )
    return [ProviderUsageRead.model_validate(r) for r in records]


@router.post(
    "",
    response_model=ProviderUsageRead,
    status_code=201,
    summary="Record provider usage (admin)",
    dependencies=[Depends(_admin_only)],
)
async def record_usage(
    body: ProviderUsageCreate, db: DbSession, current_user: CurrentUser
) -> ProviderUsageRead:
    service = ProviderUsageService(db)
    data = body.model_dump(exclude={"organization_id"})
    metadata = data.pop("metadata_", None)
    record = await service.record(
        current_user.organization_id, **data, metadata=metadata
    )
    return ProviderUsageRead.model_validate(record)


@router.get(
    "/totals",
    response_model=dict[str, float | int],
    summary="Aggregated usage totals",
)
async def usage_totals(
    db: DbSession,
    current_user: CurrentUser,
    since: datetime | None = None,
) -> dict[str, float | int]:
    service = ProviderUsageService(db)
    cutoff = since or datetime.now()
    return await service.totals_since(current_user.organization_id, since=cutoff)
