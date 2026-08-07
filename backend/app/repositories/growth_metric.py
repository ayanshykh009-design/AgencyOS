"""GrowthMetric repository (periodized growth/performance rows).

Rows are pruned after ``GROWTH_METRICS_RETENTION_DAYS`` by the retention
sweep on ``recorded_at``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth_metric import GrowthMetric
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class GrowthMetricRepository(TenantRepository[GrowthMetric]):
    """Data access for growth metrics (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GrowthMetric)

    async def list_series(
        self,
        organization_id: uuid.UUID,
        metric_type: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[GrowthMetric]:
        """Time series for one metric type within an optional window."""
        stmt = select(GrowthMetric).where(
            GrowthMetric.organization_id == organization_id,
            GrowthMetric.metric_type == metric_type,
        )
        if start is not None:
            stmt = stmt.where(GrowthMetric.recorded_at >= start)
        if end is not None:
            stmt = stmt.where(GrowthMetric.recorded_at <= end)
        stmt = stmt.order_by(GrowthMetric.recorded_at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_types(self, organization_id: uuid.UUID) -> list[str]:
        """Distinct metric types present for an organization."""
        stmt = (
            select(GrowthMetric.metric_type)
            .where(GrowthMetric.organization_id == organization_id)
            .distinct()
            .order_by(GrowthMetric.metric_type)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_older_than(self, cutoff: datetime, batch: int) -> int:
        """Prune at most ``batch`` metrics older than ``cutoff`` (retention)."""
        subq = (
            select(GrowthMetric.id)
            .where(GrowthMetric.recorded_at < cutoff)
            .order_by(GrowthMetric.recorded_at)
            .limit(max(batch, 1))
        )
        stmt = delete(GrowthMetric).where(GrowthMetric.id.in_(subq))
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0
