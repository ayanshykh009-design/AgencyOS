"""Activity endpoints: append-only audit trail (read-only for clients)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.models.enums import ActivityEventType
from app.schemas.activity import ActivityLogRead
from app.services.activity_service import ActivityService

router = APIRouter()


@router.get(
    "",
    response_model=list[ActivityLogRead],
    summary="List activity log entries",
)
async def list_activity(
    db: DbSession,
    current_user: CurrentUser,
    lead_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    event_type: ActivityEventType | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ActivityLogRead]:
    service = ActivityService(db)
    entries = await service.list_entries(
        current_user.organization_id,
        lead_id=lead_id,
        user_id=user_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return [ActivityLogRead.model_validate(e) for e in entries]
