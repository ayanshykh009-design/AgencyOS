"""GrowthForecast repository (deterministic growth forecasts)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth_forecast import GrowthForecast
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class GrowthForecastRepository(TenantRepository[GrowthForecast]):
    """Data access for growth forecasts (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GrowthForecast)

    async def list_by_type(
        self,
        organization_id: uuid.UUID,
        *,
        forecast_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrowthForecast]:
        """List forecasts, optionally by type, newest horizon first."""
        stmt = select(GrowthForecast).where(GrowthForecast.organization_id == organization_id)
        if forecast_type is not None:
            stmt = stmt.where(GrowthForecast.forecast_type == forecast_type)
        stmt = stmt.order_by(GrowthForecast.horizon_start.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_by_type(
        self, organization_id: uuid.UUID, forecast_type: str
    ) -> GrowthForecast | None:
        """The most recent forecast for a given type."""
        stmt = (
            select(GrowthForecast)
            .where(
                GrowthForecast.organization_id == organization_id,
                GrowthForecast.forecast_type == forecast_type,
            )
            .order_by(GrowthForecast.generated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_type(self, organization_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(GrowthForecast.forecast_type, func.count(GrowthForecast.id))
            .where(GrowthForecast.organization_id == organization_id)
            .group_by(GrowthForecast.forecast_type)
        )
        result = await self._session.execute(stmt)
        return {ftype: int(count) for ftype, count in result.all()}
