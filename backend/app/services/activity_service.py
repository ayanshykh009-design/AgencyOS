"""ActivityLog service: append-only audit trail."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType
from app.repositories.activity_log import ActivityLogRepository
from app.services.base import commit_with_retry, utcnow


class ActivityService:
    """Owns activity-log rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._logs = ActivityLogRepository(session)

    async def record(
        self,
        organization_id: uuid.UUID,
        *,
        event_type: ActivityEventType,
        user_id: uuid.UUID | None = None,
        lead_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActivityLog:
        entry = ActivityLog(
            organization_id=organization_id,
            user_id=user_id,
            lead_id=lead_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            metadata_=metadata or {},
            occurred_at=utcnow(),
        )
        self._logs.add(entry)
        await commit_with_retry(self._session)
        return entry

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        event_type: ActivityEventType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        return await self._logs.list(
            organization_id,
            lead_id=lead_id,
            user_id=user_id,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )
