"""GrowthScenario repository (saved what-if projections, M7)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth_scenario import GrowthScenario
from app.repositories.base import TenantRepository


class GrowthScenarioRepository(TenantRepository[GrowthScenario]):
    """Data access for growth scenarios (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GrowthScenario)

    async def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        forecast_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrowthScenario]:
        """List scenarios, newest first, optionally anchored to a forecast."""
        stmt = select(GrowthScenario).where(GrowthScenario.organization_id == organization_id)
        if forecast_id is not None:
            stmt = stmt.where(GrowthScenario.forecast_id == forecast_id)
        stmt = stmt.order_by(GrowthScenario.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
