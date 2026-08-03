"""Audit endpoints: enriched, admin-only read of the activity trail."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import ActivityEventType
from app.schemas.activity import ActivityLogRead
from app.services.activity_service import ActivityService

router = APIRouter()

_audit = Depends(require_permission(Permission.AUDIT_READ))


def _read(entry: object) -> ActivityLogRead:
    """Serialize an audit entry, resolving actor metadata when available."""
    model = ActivityLogRead.model_validate(entry)
    user = getattr(entry, "user", None)
    if user is not None:
        model.actor_user_id = getattr(user, "id", None)
        model.actor_name = getattr(user, "full_name", None) or getattr(
            user, "email", None
        )
    return model


@router.get(
    "",
    response_model=list[ActivityLogRead],
    summary="List audit trail with actor metadata",
    dependencies=[_audit],
)
async def list_audit(
    db: DbSession,
    current_user: CurrentUser,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    event_type: ActivityEventType | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ActivityLogRead]:
    service = ActivityService(db)
    entries = await service.audit_trail(
        current_user.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        lead_id=lead_id,
        user_id=user_id,
        event_type=event_type,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        limit=limit,
        offset=offset,
    )
    return [_read(entry) for entry in entries]


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=list[ActivityLogRead],
    summary="Audit trail for one entity",
    dependencies=[_audit],
)
async def entity_audit(
    entity_type: str,
    entity_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    event_type: ActivityEventType | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ActivityLogRead]:
    service = ActivityService(db)
    entries = await service.audit_trail(
        current_user.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return [_read(entry) for entry in entries]
