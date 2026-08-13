"""GrowthAnalysis repository (deterministic analysis snapshots, M7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import GrowthAnalysisStatus, GrowthAnalysisType
from app.models.growth_analysis import GrowthAnalysis
from app.repositories.base import TenantRepository


class GrowthAnalysisRepository(TenantRepository[GrowthAnalysis]):
    """Data access for growth analyses (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GrowthAnalysis)

    async def list_by_filters(
        self,
        organization_id: uuid.UUID,
        *,
        analysis_type: GrowthAnalysisType | None = None,
        status: GrowthAnalysisStatus | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrowthAnalysis]:
        """List analyses, newest first, with optional type/status/window filters."""
        stmt = select(GrowthAnalysis).where(GrowthAnalysis.organization_id == organization_id)
        if analysis_type is not None:
            stmt = stmt.where(GrowthAnalysis.analysis_type == analysis_type)
        if status is not None:
            stmt = stmt.where(GrowthAnalysis.status == status)
        if start is not None:
            stmt = stmt.where(GrowthAnalysis.period_start >= start)
        if end is not None:
            stmt = stmt.where(GrowthAnalysis.period_end <= end)
        stmt = stmt.order_by(GrowthAnalysis.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_type(
        self,
        organization_id: uuid.UUID,
        analysis_type: GrowthAnalysisType,
        *,
        status: GrowthAnalysisStatus = GrowthAnalysisStatus.COMPLETED,
    ) -> GrowthAnalysis | None:
        """The most recent completed snapshot of a given type."""
        stmt = (
            select(GrowthAnalysis)
            .where(
                GrowthAnalysis.organization_id == organization_id,
                GrowthAnalysis.analysis_type == analysis_type,
                GrowthAnalysis.status == status,
            )
            .order_by(GrowthAnalysis.generated_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
