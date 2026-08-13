"""LeadSource endpoints (org-scoped CRUD)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, require_role
from app.models.enums import UserRole
from app.schemas.lead_source import LeadSourceCreate, LeadSourceRead, LeadSourceUpdate
from app.services.lead_source_service import LeadSourceService

router = APIRouter()

_admin_only = require_role(UserRole.OWNER, UserRole.ADMIN)


@router.get(
    "",
    response_model=list[LeadSourceRead],
    summary="List lead sources",
)
async def list_sources(
    db: DbSession,
    current_user: CurrentUser,
    include_inactive: bool = True,
) -> list[LeadSourceRead]:
    service = LeadSourceService(db)
    sources = await service.list(current_user.organization_id, include_inactive=include_inactive)
    return [LeadSourceRead.model_validate(s) for s in sources]


@router.post(
    "",
    response_model=LeadSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lead source",
    dependencies=[Depends(_admin_only)],
)
async def create_source(
    body: LeadSourceCreate, db: DbSession, current_user: CurrentUser
) -> LeadSourceRead:
    service = LeadSourceService(db)
    source = await service.create(current_user.organization_id, body.model_dump())
    return LeadSourceRead.model_validate(source)


@router.get(
    "/{source_id}",
    response_model=LeadSourceRead,
    summary="Get a lead source",
)
async def get_source(
    source_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> LeadSourceRead:
    service = LeadSourceService(db)
    source = await service.get(current_user.organization_id, source_id)
    return LeadSourceRead.model_validate(source)


@router.patch(
    "/{source_id}",
    response_model=LeadSourceRead,
    summary="Update a lead source",
    dependencies=[Depends(_admin_only)],
)
async def update_source(
    source_id: uuid.UUID,
    body: LeadSourceUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> LeadSourceRead:
    service = LeadSourceService(db)
    source = await service.update(
        current_user.organization_id,
        source_id,
        body.model_dump(exclude_unset=True),
    )
    return LeadSourceRead.model_validate(source)
