"""Repositories for lead assignment rules and history."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import LeadAssignmentLog, LeadAssignmentRule


class AssignmentRuleRepository:
    """Data access for the per-org assignment rule."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID) -> LeadAssignmentRule | None:
        stmt = select(LeadAssignmentRule).where(
            LeadAssignmentRule.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, rule: LeadAssignmentRule) -> None:
        self._session.add(rule)


class AssignmentLogRepository:
    """Append-only data access for assignment history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, entry: LeadAssignmentLog) -> None:
        self._session.add(entry)

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        lead_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LeadAssignmentLog]:
        stmt = (
            select(LeadAssignmentLog)
            .where(
                LeadAssignmentLog.organization_id == organization_id,
                LeadAssignmentLog.lead_id == lead_id,
            )
            .order_by(LeadAssignmentLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
