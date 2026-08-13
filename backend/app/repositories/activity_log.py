"""ActivityLog repository (append-only audit trail)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType


class ActivityLogRepository:
    """Data access for activity logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, entry: ActivityLog) -> None:
        self._session.add(entry)

    async def list_entries(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        event_type: ActivityEventType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        stmt = select(ActivityLog).where(ActivityLog.organization_id == organization_id)
        if lead_id is not None:
            stmt = stmt.where(ActivityLog.lead_id == lead_id)
        if user_id is not None:
            stmt = stmt.where(ActivityLog.user_id == user_id)
        if event_type is not None:
            stmt = stmt.where(ActivityLog.event_type == event_type)
        stmt = stmt.order_by(ActivityLog.occurred_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def audit_list(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        lead_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        event_type: ActivityEventType | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        """Audit-oriented list with the acting user eagerly loaded."""
        stmt = (
            select(ActivityLog)
            .options(selectinload(ActivityLog.user))
            .where(ActivityLog.organization_id == organization_id)
        )
        if entity_type is not None:
            stmt = stmt.where(ActivityLog.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ActivityLog.entity_id == entity_id)
        if lead_id is not None:
            stmt = stmt.where(ActivityLog.lead_id == lead_id)
        if user_id is not None:
            stmt = stmt.where(ActivityLog.user_id == user_id)
        if event_type is not None:
            stmt = stmt.where(ActivityLog.event_type == event_type)
        if occurred_after is not None:
            stmt = stmt.where(ActivityLog.occurred_at >= occurred_after)
        if occurred_before is not None:
            stmt = stmt.where(ActivityLog.occurred_at <= occurred_before)
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

    async def count_by_event_type(self, event_type: ActivityEventType, since: datetime) -> int:
        """Count events of one type occurred at/after ``since`` (all orgs).

        Used for operator-level lifecycle statistics where the acting
        organization is the operator tenant, not a customer tenant.
        """
        stmt = (
            select(func.count(ActivityLog.id))
            .where(
                ActivityLog.event_type == event_type,
                ActivityLog.occurred_at >= since,
            )
            .select_from(ActivityLog)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
