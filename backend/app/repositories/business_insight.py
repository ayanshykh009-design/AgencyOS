"""BusinessInsight repository (generated business insight rows)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_insight import BusinessInsight
from app.models.enums import InsightSeverity, InsightStatus, InsightType
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass


class BusinessInsightRepository(TenantRepository[BusinessInsight]):
    """Data access for business insights (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BusinessInsight)

    async def list_by_status(
        self,
        organization_id: uuid.UUID,
        *,
        status: InsightStatus | None = None,
        severity: InsightSeverity | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BusinessInsight]:
        """List insights, optionally filtered by status/severity, newest first."""
        stmt = select(BusinessInsight).where(
            BusinessInsight.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(BusinessInsight.status == status)
        if severity is not None:
            stmt = stmt.where(BusinessInsight.severity == severity)
        stmt = stmt.order_by(BusinessInsight.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_open(self, organization_id: uuid.UUID) -> int:
        """Active (unacknowledged) insight count."""
        stmt = (
            select(func.count(BusinessInsight.id))
            .where(
                BusinessInsight.organization_id == organization_id,
                BusinessInsight.status == InsightStatus.ACTIVE,
            )
            .select_from(BusinessInsight)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_by_type(
        self, organization_id: uuid.UUID
    ) -> dict[InsightType, int]:
        stmt = (
            select(BusinessInsight.insight_type, func.count(BusinessInsight.id))
            .where(BusinessInsight.organization_id == organization_id)
            .group_by(BusinessInsight.insight_type)
        )
        result = await self._session.execute(stmt)
        return {itype: int(count) for itype, count in result.all()}
