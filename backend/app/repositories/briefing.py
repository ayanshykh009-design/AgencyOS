"""Briefing repository (generated founder briefings)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.briefing import Briefing
from app.models.enums import BriefingType
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class BriefingRepository(TenantRepository[Briefing]):
    """Data access for founder briefings (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Briefing)

    async def list_by_type(
        self,
        organization_id: uuid.UUID,
        *,
        briefing_type: BriefingType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Briefing]:
        """List briefings, optionally by cadence, newest first."""
        stmt = select(Briefing).where(Briefing.organization_id == organization_id)
        if briefing_type is not None:
            stmt = stmt.where(Briefing.briefing_type == briefing_type)
        stmt = stmt.order_by(Briefing.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_by_type(
        self, organization_id: uuid.UUID, briefing_type: BriefingType
    ) -> Briefing | None:
        """The most recent briefing of a given cadence."""
        stmt = (
            select(Briefing)
            .where(
                Briefing.organization_id == organization_id,
                Briefing.briefing_type == briefing_type,
            )
            .order_by(Briefing.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_type(self, organization_id: uuid.UUID) -> dict[BriefingType, int]:
        stmt = (
            select(Briefing.briefing_type, func.count(Briefing.id))
            .where(Briefing.organization_id == organization_id)
            .group_by(Briefing.briefing_type)
        )
        result = await self._session.execute(stmt)
        return {btype: int(count) for btype, count in result.all()}
