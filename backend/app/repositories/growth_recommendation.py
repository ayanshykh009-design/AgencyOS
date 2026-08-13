"""GrowthRecommendation repository (evidence-backed recommendations, M7)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RecommendationPriority, RecommendationStatus
from app.models.growth_recommendation import GrowthRecommendation
from app.repositories.base import TenantRepository


class GrowthRecommendationRepository(TenantRepository[GrowthRecommendation]):
    """Data access for growth recommendations (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GrowthRecommendation)

    async def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        status: RecommendationStatus | None = None,
        priority: RecommendationPriority | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrowthRecommendation]:
        """List recommendations, active-then-priority order by default."""
        stmt = select(GrowthRecommendation).where(
            GrowthRecommendation.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(GrowthRecommendation.status == status)
        if priority is not None:
            stmt = stmt.where(GrowthRecommendation.priority == priority)
        stmt = stmt.order_by(
            GrowthRecommendation.status.asc(),
            GrowthRecommendation.priority.asc(),
            GrowthRecommendation.created_at.desc(),
        )
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, organization_id: uuid.UUID) -> dict[RecommendationStatus, int]:
        """Recommendation counts per triage status."""
        stmt = (
            select(GrowthRecommendation.status, func.count(GrowthRecommendation.id))
            .where(GrowthRecommendation.organization_id == organization_id)
            .group_by(GrowthRecommendation.status)
        )
        result = await self._session.execute(stmt)
        return {status: int(count) for status, count in result.all()}
