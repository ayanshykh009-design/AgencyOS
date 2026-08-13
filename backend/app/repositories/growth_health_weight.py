"""GrowthHealthWeight repository (versioned health weights, M7)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth_health_weight import GrowthHealthWeight
from app.repositories.base import TenantRepository


class GrowthHealthWeightRepository(TenantRepository[GrowthHealthWeight]):
    """Data access for growth health weights (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GrowthHealthWeight)

    async def active(self, organization_id: uuid.UUID) -> GrowthHealthWeight | None:
        """The currently active weight set for an org (or None)."""
        stmt = select(GrowthHealthWeight).where(
            GrowthHealthWeight.organization_id == organization_id,
            GrowthHealthWeight.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_versions(
        self, organization_id: uuid.UUID, *, limit: int = 50
    ) -> list[GrowthHealthWeight]:
        """All weight versions, newest first."""
        stmt = (
            select(GrowthHealthWeight)
            .where(GrowthHealthWeight.organization_id == organization_id)
            .order_by(GrowthHealthWeight.version.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate_all(self, organization_id: uuid.UUID) -> None:
        """Deactivate every weight version for an org (prepares activation)."""
        await self._session.execute(
            update(GrowthHealthWeight)
            .where(GrowthHealthWeight.organization_id == organization_id)
            .values(is_active=False)
        )
