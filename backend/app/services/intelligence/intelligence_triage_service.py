"""IntelligenceTriageService — the M9 sweep (write side of the triage layer).

Each per-org sweep is deterministic and idempotent:

1. **collect** — read M7/M8 output within the analysis window (active growth
   recommendations, active business insights, completed growth analyses) plus
   bounded pipeline condition detectors (high-value deals).
2. **normalize + score** — map each source to a :class:`SignalCandidate`,
   compute the versioned ``priority_score``, and sort by score descending.
3. **sync** — upsert by ``content_hash`` (concurrency-safe against the partial
   unique index), then supersede active signals whose hash is no longer
   emitted. Acknowledged/dismissed signals are never touched.

The service never writes M7/M8 source tables and never recomputes metrics.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import (
    GrowthAnalysisStatus,
    InsightStatus,
    IntelligenceSignalStatus,
    LeadStatus,
    RecommendationStatus,
)
from app.models.intelligence_signal import IntelligenceSignal
from app.repositories.business_insight import BusinessInsightRepository
from app.repositories.growth_analysis import GrowthAnalysisRepository
from app.repositories.growth_recommendation import GrowthRecommendationRepository
from app.repositories.intelligence_signal import IntelligenceSignalRepository
from app.repositories.lead import LeadRepository
from app.services.base import utcnow
from app.services.intelligence.signal_normalizer import (
    PIPELINE_FRESH_DAYS,
    PIPELINE_LEAD_SCAN_CAP,
    PIPELINE_STUCK_DAYS,
    PIPELINE_VALUE_THRESHOLD,
    SignalCandidate,
    SignalNormalizer,
)
from app.services.intelligence.triage_scorer import TriageScorer

logger = logging.getLogger("agencyos.intelligence")

_PIPELINE_STATUSES = [LeadStatus.MEETING_BOOKED, LeadStatus.PROPOSAL_SENT]


class IntelligenceTriageService:
    """Orchestrates one deterministic, idempotent triage sweep per org."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IntelligenceSignalRepository(session)
        self._normalizer = SignalNormalizer()
        self._scorer = TriageScorer()

    async def candidate_orgs(self) -> list[uuid.UUID]:
        """Orgs to sweep this tick, oldest-created first (bounded fair-drain)."""
        return await self._repo.candidate_orgs(
            limit=settings.INTELLIGENCE_TRIAGE_ORGS_PER_SWEEP,
            pipeline_statuses=_PIPELINE_STATUSES,
            min_deal_value=Decimal(str(PIPELINE_VALUE_THRESHOLD)),
        )

    async def collect_candidates(
        self, organization_id: uuid.UUID, *, now: datetime
    ) -> list[SignalCandidate]:
        """Gather deterministic candidates from M7/M8 output + pipeline rules."""
        window_start = now - timedelta(days=settings.INTELLIGENCE_TRIAGE_WINDOW_DAYS)
        cap = settings.INTELLIGENCE_TRIAGE_MAX_SIGNALS_PER_ORG

        candidates: list[SignalCandidate] = []
        recommendations = await GrowthRecommendationRepository(
            self._session
        ).list_for_org(
            organization_id,
            status=RecommendationStatus.ACTIVE,
            limit=cap,
        )
        for rec in recommendations:
            candidates.append(self._normalizer.normalize_recommendation(rec))

        insights = await BusinessInsightRepository(self._session).list_by_status(
            organization_id,
            status=InsightStatus.ACTIVE,
            limit=cap,
        )
        for insight in insights:
            candidates.append(self._normalizer.normalize_insight(insight))

        analyses = await GrowthAnalysisRepository(self._session).list_by_filters(
            organization_id,
            status=GrowthAnalysisStatus.COMPLETED,
            start=window_start,
            limit=cap,
        )
        for analysis in analyses:
            candidates.append(self._normalizer.normalize_analysis(analysis))

        leads = await LeadRepository(self._session).list_for_intelligence(
            organization_id,
            statuses=_PIPELINE_STATUSES,
            min_deal_value=Decimal(str(PIPELINE_VALUE_THRESHOLD)),
            limit=PIPELINE_LEAD_SCAN_CAP,
        )
        for lead in leads:
            age = (now - lead.updated_at).total_seconds() / 86400
            if lead.status == LeadStatus.PROPOSAL_SENT and age <= PIPELINE_FRESH_DAYS:
                candidates.append(
                    self._normalizer.normalize_pipeline_fact(
                        lead, rule="fresh_high_value_proposal"
                    )
                )
            elif age > PIPELINE_STUCK_DAYS:
                candidates.append(
                    self._normalizer.normalize_pipeline_fact(lead, rule="stuck_high_value")
                )

        return candidates

    async def run_sweep_for_org(
        self, organization_id: uuid.UUID, *, now: datetime | None = None
    ) -> dict[str, int]:
        """Run one full sweep for a single org; returns counters.

        The caller owns the transaction boundary (commit/rollback). On a
        concurrent duplicate insert (partial unique index) the sync is retried
        against the winner's row, so two workers sweeping the same org cannot
        create duplicates or lose the update.
        """
        now = now or utcnow()
        counters = {
            "candidates": 0,
            "created": 0,
            "updated": 0,
            "superseded": 0,
            "high_priority": 0,
        }

        collected = await self.collect_candidates(organization_id, now=now)
        by_hash: dict[str, SignalCandidate] = {}
        for candidate in collected:
            by_hash.setdefault(candidate.content_hash, candidate)

        cap = settings.INTELLIGENCE_TRIAGE_MAX_SIGNALS_PER_ORG
        candidates = list(by_hash.values())[:cap]

        scored: list[tuple[SignalCandidate, float, dict]] = []
        for candidate in candidates:
            score, components = self._scorer.score(candidate, now=now)
            scored.append((candidate, score, components))
        scored.sort(key=lambda item: item[1], reverse=True)

        counters["candidates"] = len(scored)
        counters["high_priority"] = sum(1 for _, score, _ in scored if score >= 0.7)

        live_hashes = {candidate.content_hash for candidate, _, _ in scored}
        for attempt in range(2):
            try:
                created, updated = await self._sync_once(organization_id, scored, now=now)
                await self._session.flush()
                superseded = await self._repo.supersede_stale(organization_id, live_hashes)
                await self._session.flush()
                counters["created"] = created
                counters["updated"] = updated
                counters["superseded"] = superseded
                return counters
            except IntegrityError:
                # A concurrent worker inserted the same hash. Roll back and
                # re-run: the retry now finds the winner's row and updates it,
                # so concurrent sweeps can never duplicate or lose a signal.
                await self._session.rollback()
                if attempt == 1:
                    raise
        return counters  # pragma: no cover - unreachable

    async def _sync_once(
        self,
        organization_id: uuid.UUID,
        scored: list[tuple[SignalCandidate, float, dict]],
        *,
        now: datetime,
    ) -> tuple[int, int]:
        """Upsert candidates by content hash (caller owns concurrency retry)."""
        created = 0
        updated = 0
        for candidate, score, components in scored:
            existing = await self._repo.get_live_by_hash(organization_id, candidate.content_hash)
            if existing is None:
                self._repo.add(
                    IntelligenceSignal(
                        organization_id=organization_id,
                        signal_category=candidate.signal_category,
                        source_type=candidate.source_type,
                        source_row_id=candidate.source_row_id,
                        title=candidate.title,
                        summary=candidate.summary,
                        severity=candidate.severity,
                        business_impact=candidate.business_impact,
                        priority_score=score,
                        priority_components=components,
                        evidence=candidate.evidence,
                        recommended_next_step=candidate.recommended_next_step,
                        confidence=candidate.confidence,
                        status=IntelligenceSignalStatus.ACTIVE,
                        content_hash=candidate.content_hash,
                        last_triaged_at=now,
                    )
                )
                created += 1
            else:
                existing.signal_category = candidate.signal_category
                existing.source_row_id = candidate.source_row_id
                existing.title = candidate.title
                existing.summary = candidate.summary
                existing.severity = candidate.severity
                existing.business_impact = candidate.business_impact
                existing.priority_score = score
                existing.priority_components = components
                existing.evidence = candidate.evidence
                existing.recommended_next_step = candidate.recommended_next_step
                existing.confidence = candidate.confidence
                existing.last_triaged_at = now
                updated += 1
        return created, updated
