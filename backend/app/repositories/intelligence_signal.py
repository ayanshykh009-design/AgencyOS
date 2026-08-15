"""IntelligenceSignal repository (Founder Intelligence & Growth Triage, M9)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select, union_all, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    IntelligenceSignalStatus,
    LeadStatus,
    SignalCategory,
    SignalSourceType,
)
from app.models.intelligence_signal import IntelligenceSignal
from app.repositories.base import TenantRepository

# Deterministic triage bands (must match app/services/intelligence/triage_scorer.py).
_HIGH_BAND = 0.7
_MEDIUM_BAND = 0.45


class IntelligenceSignalRepository(TenantRepository[IntelligenceSignal]):
    """Data access for intelligence signals (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, IntelligenceSignal)

    async def get_live_by_hash(
        self, organization_id: uuid.UUID, content_hash: str
    ) -> IntelligenceSignal | None:
        """Fetch the single live (non-superseded) signal for a content hash."""
        stmt = select(IntelligenceSignal).where(
            IntelligenceSignal.organization_id == organization_id,
            IntelligenceSignal.content_hash == content_hash,
            IntelligenceSignal.status != IntelligenceSignalStatus.SUPERSEDED,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        status: IntelligenceSignalStatus | None = None,
        category: SignalCategory | None = None,
        source_type: SignalSourceType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IntelligenceSignal]:
        """List signals, priority-first (active before archived at equal score)."""
        stmt = select(IntelligenceSignal).where(
            IntelligenceSignal.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(IntelligenceSignal.status == status)
        if category is not None:
            stmt = stmt.where(IntelligenceSignal.signal_category == category)
        if source_type is not None:
            stmt = stmt.where(IntelligenceSignal.source_type == source_type)
        stmt = stmt.order_by(
            IntelligenceSignal.status.asc(),
            IntelligenceSignal.priority_score.desc(),
            IntelligenceSignal.created_at.desc(),
        )
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(
        self, organization_id: uuid.UUID
    ) -> dict[IntelligenceSignalStatus, int]:
        """Signal counts per triage status (single aggregate query)."""
        stmt = (
            select(IntelligenceSignal.status, func.count(IntelligenceSignal.id))
            .where(IntelligenceSignal.organization_id == organization_id)
            .group_by(IntelligenceSignal.status)
        )
        result = await self._session.execute(stmt)
        counts = {IntelligenceSignalStatus.ACTIVE: 0,
                  IntelligenceSignalStatus.ACKNOWLEDGED: 0,
                  IntelligenceSignalStatus.DISMISSED: 0,
                  IntelligenceSignalStatus.SUPERSEDED: 0}
        for status, count in result.all():
            counts[status] = int(count)
        return counts

    async def priority_band_counts(
        self, organization_id: uuid.UUID, *, status: IntelligenceSignalStatus
    ) -> tuple[int, int, int]:
        """(high, medium, low) band counts for one status, priority-first."""
        stmt = (
            select(
                func.count(IntelligenceSignal.id).filter(
                    IntelligenceSignal.priority_score >= _HIGH_BAND
                ),
                func.count(IntelligenceSignal.id).filter(
                    IntelligenceSignal.priority_score >= _MEDIUM_BAND,
                    IntelligenceSignal.priority_score < _HIGH_BAND,
                ),
                func.count(IntelligenceSignal.id).filter(
                    IntelligenceSignal.priority_score < _MEDIUM_BAND
                ),
            )
            .where(
                IntelligenceSignal.organization_id == organization_id,
                IntelligenceSignal.status == status,
            )
        )
        result = await self._session.execute(stmt)
        high, medium, low = result.one()
        return int(high), int(medium), int(low)

    async def highest_priority_score(
        self, organization_id: uuid.UUID, *, status: IntelligenceSignalStatus
    ) -> float | None:
        """Highest priority score across signals with the given status."""
        stmt = (
            select(func.max(IntelligenceSignal.priority_score))
            .where(
                IntelligenceSignal.organization_id == organization_id,
                IntelligenceSignal.status == status,
            )
        )
        result = await self._session.execute(stmt)
        value = result.scalar_one_or_none()
        return float(value) if value is not None else None

    async def count_live(self, organization_id: uuid.UUID) -> int:
        """Count active + acknowledged signals (the per-org cap surface)."""
        stmt = (
            select(func.count(IntelligenceSignal.id))
            .where(
                IntelligenceSignal.organization_id == organization_id,
                IntelligenceSignal.status.in_(
                    [IntelligenceSignalStatus.ACTIVE, IntelligenceSignalStatus.ACKNOWLEDGED]
                ),
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def candidate_orgs(
        self,
        *,
        limit: int = 20,
        pipeline_statuses: list[LeadStatus],
        min_deal_value: Decimal,
    ) -> list[uuid.UUID]:
        """Organizations that may need a triage sweep, oldest-created first.

        Candidate sources: active growth recommendations, active business
        insights, completed growth analyses, leads matching the pipeline
        condition detectors, and orgs that already hold live signals (so stale
        signals get superseded even after their source goes quiet).
        """
        from app.models.business_insight import BusinessInsight
        from app.models.enums import GrowthAnalysisStatus, InsightStatus, RecommendationStatus
        from app.models.growth_analysis import GrowthAnalysis
        from app.models.growth_recommendation import GrowthRecommendation
        from app.models.lead import Lead
        from app.models.organization import Organization

        candidate_org_ids = union_all(
            select(GrowthRecommendation.organization_id).where(
                GrowthRecommendation.status == RecommendationStatus.ACTIVE
            ),
            select(BusinessInsight.organization_id).where(
                BusinessInsight.status == InsightStatus.ACTIVE
            ),
            select(GrowthAnalysis.organization_id).where(
                GrowthAnalysis.status == GrowthAnalysisStatus.COMPLETED
            ),
            select(Lead.organization_id).where(
                Lead.deleted_at.is_(None),
                Lead.status.in_(pipeline_statuses),
                Lead.deal_value.is_not(None),
                Lead.deal_value >= min_deal_value,
            ),
            select(IntelligenceSignal.organization_id).where(
                IntelligenceSignal.status == IntelligenceSignalStatus.ACTIVE
            ),
        ).subquery()
        stmt = (
            select(Organization.id)
            .where(Organization.id.in_(select(candidate_org_ids.c.organization_id)))
            .order_by(Organization.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def supersede_stale(
        self, organization_id: uuid.UUID, live_hashes: set[str]
    ) -> int:
        """Supersede active signals whose content hash is no longer emitted.

        ``live_hashes`` is the set of deterministic hashes produced by the
        current sweep; any ACTIVE signal outside it describes a source that no
        longer warrants attention. Acknowledged/dismissed signals are left
        untouched (they are the founder's record).
        """
        if not live_hashes:
            stmt = update(IntelligenceSignal).where(
                IntelligenceSignal.organization_id == organization_id,
                IntelligenceSignal.status == IntelligenceSignalStatus.ACTIVE,
            )
        else:
            stmt = update(IntelligenceSignal).where(
                IntelligenceSignal.organization_id == organization_id,
                IntelligenceSignal.status == IntelligenceSignalStatus.ACTIVE,
                IntelligenceSignal.content_hash.not_in(list(live_hashes)),
            )
        stmt = stmt.values(status=IntelligenceSignalStatus.SUPERSEDED)
        result = cast(CursorResult, await self._session.execute(stmt))
        return int(result.rowcount or 0)

    async def set_status(
        self,
        organization_id: uuid.UUID,
        signal_id: uuid.UUID,
        status: IntelligenceSignalStatus,
        *,
        acknowledged_by_user_id: uuid.UUID | None = None,
        acknowledged_at=None,
    ) -> IntelligenceSignal | None:
        """Transition a signal to a founder-driven status (acknowledge/dismiss).

        Returns the updated row (the caller re-reads it after the flush so
        server-side defaults are loaded), or None when not found.
        """
        stmt = (
            update(IntelligenceSignal)
            .where(
                IntelligenceSignal.organization_id == organization_id,
                IntelligenceSignal.id == signal_id,
            )
            .values(
                status=status,
                acknowledged_by_user_id=acknowledged_by_user_id,
                acknowledged_at=acknowledged_at,
            )
            .returning(IntelligenceSignal.id)
        )
        result = await self._session.execute(stmt)
        updated_id = result.scalar_one_or_none()
        if updated_id is None:
            return None
        await self._session.flush()
        return await self.get(organization_id, updated_id)
