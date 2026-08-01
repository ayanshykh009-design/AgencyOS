"""ActivityLog repository (append-only audit trail)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType


class ActivityLogRepository:
    """Data access for activity logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, entry: ActivityLog) -> None:
        self._session.add(entry)

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
        stmt = select(ActivityLog).where(
            ActivityLog.organization_id == organization_id
        )
        if lead_id is not None:
            stmt = stmt.where(ActivityLog.lead_id == lead_id)
        if user_id is not None:
            stmt = stmt.where(ActivityLog.user_id == user_id)
        if event_type is not None:
            stmt = stmt.where(ActivityLog.event_type == event_type)
        stmt = stmt.order_by(ActivityLog.occurred_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        organization_id: uuid.UUID,
        *,
        since=None,
        event_type: ActivityEventType | None = None,
    ) -> int:
        stmt = (
            select(func.count(ActivityLog.id))
            .where(ActivityLog.organization_id == organization_id)
            .select_from(ActivityLog)
        )
        if since is not None:
            stmt = stmt.where(ActivityLog.occurred_at >= since)
        if event_type is not None:
            stmt = stmt.where(ActivityLog.event_type == event_type)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
