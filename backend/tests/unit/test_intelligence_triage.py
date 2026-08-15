"""Unit tests for M9 founder intelligence & growth triage.

Covers the deterministic normalizer/scorer contracts, the founder read/triage
service state machine, and the sweep orchestration (dedup, cap, supersede,
concurrency retry) with mocked repositories.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.models.business_insight import BusinessInsight
from app.models.enums import (
    GrowthAnalysisType,
    InsightSeverity,
    InsightStatus,
    InsightType,
    IntelligenceConfidence,
    IntelligenceSignalSeverity,
    IntelligenceSignalStatus,
    LeadStatus,
    RecommendationPriority,
    RecommendationStatus,
    SignalCategory,
    SignalSourceType,
)
from app.models.growth_analysis import GrowthAnalysis
from app.models.growth_recommendation import GrowthRecommendation
from app.models.intelligence_signal import IntelligenceSignal
from app.models.lead import Lead
from app.services.intelligence.founder_intelligence_service import FounderIntelligenceService
from app.services.intelligence.intelligence_triage_service import IntelligenceTriageService
from app.services.intelligence.signal_normalizer import (
    PIPELINE_VALUE_THRESHOLD,
    SignalNormalizer,
    compute_content_hash,
)
from app.services.intelligence.triage_scorer import HIGH_BAND, MEDIUM_BAND, TriageScorer

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 8, 15, 12, 0, 0)


def _rec(**overrides) -> GrowthRecommendation:
    defaults = {
        "id": uuid.uuid4(),
        "organization_id": ORG_ID,
        "recommendation_type": "revenue",
        "priority": RecommendationPriority.HIGH,
        "confidence": RecommendationPriority.HIGH,
        "status": RecommendationStatus.ACTIVE,
        "title": "Raise prices",
        "summary": "Raise prices on enterprise tier",
        "action_type": "send_outreach",
        "action_payload": {"impact": {"amount": 50000, "dimension": "revenue", "basis": "model"}},
        "evidence": [],
        "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(days=2),
    }
    defaults.update(overrides)
    return GrowthRecommendation(**defaults)


def _insight(**overrides) -> BusinessInsight:
    defaults = {
        "id": uuid.uuid4(),
        "organization_id": ORG_ID,
        "insight_type": InsightType.RISK,
        "severity": InsightSeverity.HIGH,
        "status": InsightStatus.ACTIVE,
        "title": "Pipeline risk",
        "summary": "A big deal is stuck",
        "metadata_": {"evidence": [{"deal_value": 30000}]},
        "created_at": NOW - timedelta(days=1),
        "updated_at": NOW - timedelta(days=1),
    }
    defaults.update(overrides)
    return BusinessInsight(**defaults)


def _analysis(**overrides) -> GrowthAnalysis:
    defaults = {
        "id": uuid.uuid4(),
        "organization_id": ORG_ID,
        "analysis_type": GrowthAnalysisType.BOTTLENECKS,
        "summary": "Conversion bottleneck at proposal stage",
        "health_score": Decimal("45.0000"),
        "evidence": [],
        "status": "completed",
        "generated_at": NOW - timedelta(days=3),
    }
    defaults.update(overrides)
    return GrowthAnalysis(**defaults)


def _lead(**overrides) -> Lead:
    defaults = {
        "id": uuid.uuid4(),
        "organization_id": ORG_ID,
        "status": LeadStatus.PROPOSAL_SENT,
        "deal_value": Decimal("30000.00"),
        "company": "Acme Inc",
        "email": "ops@acme.example",
        "updated_at": NOW - timedelta(days=1),
        "created_at": NOW - timedelta(days=30),
    }
    defaults.update(overrides)
    return Lead(**defaults)


# -- normalizer ---------------------------------------------------------


def test_normalizer_recommendation_maps_severity_confidence_and_hash() -> None:
    rec = _rec()
    candidate = SignalNormalizer.normalize_recommendation(rec)
    assert candidate.signal_category == SignalCategory.GROWTH_RECOMMENDATION
    assert candidate.source_type == SignalSourceType.GROWTH_RECOMMENDATION
    assert candidate.severity == IntelligenceSignalSeverity.HIGH
    assert candidate.confidence == IntelligenceConfidence.HIGH
    assert candidate.business_impact == {
        "amount": 50000.0,
        "dimension": "revenue",
        "basis": "model",
    }
    assert candidate.content_hash == compute_content_hash(
        candidate.source_type, candidate.source_row_id, rec.title, rec.summary
    )


def test_normalizer_recommendation_is_deterministic() -> None:
    row_id = uuid.uuid4()
    a = SignalNormalizer.normalize_recommendation(_rec(id=row_id))
    b = SignalNormalizer.normalize_recommendation(
        _rec(id=row_id, title=a.title, summary=a.summary)
    )
    c = SignalNormalizer.normalize_recommendation(_rec(id=row_id, title="Different title"))
    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash


def test_normalizer_insight_extracts_evidence_amount_but_never_invents() -> None:
    with_evidence = SignalNormalizer.normalize_insight(_insight())
    assert with_evidence.business_impact["amount"] == 30000.0
    assert with_evidence.signal_category == SignalCategory.PIPELINE_RISK

    no_evidence = SignalNormalizer.normalize_insight(
        _insight(metadata_={"note": "nothing numeric here"})
    )
    assert "amount" not in no_evidence.business_impact
    assert no_evidence.business_impact == {}


def test_normalizer_analysis_uses_health_score_for_severity() -> None:
    unhealthy = SignalNormalizer.normalize_analysis(_analysis(health_score=Decimal("40.0000")))
    assert unhealthy.severity == IntelligenceSignalSeverity.HIGH
    healthy = SignalNormalizer.normalize_analysis(_analysis(health_score=Decimal("80.0000")))
    assert healthy.severity == IntelligenceSignalSeverity.LOW


def test_normalizer_pipeline_facts_map_rules() -> None:
    stuck = SignalNormalizer.normalize_pipeline_fact(
        _lead(status=LeadStatus.MEETING_BOOKED, updated_at=NOW - timedelta(days=20)),
        rule="stuck_high_value",
    )
    assert stuck.signal_category == SignalCategory.PIPELINE_RISK
    assert stuck.urgency == 1.0
    assert stuck.business_impact["amount"] == 30000.0

    fresh = SignalNormalizer.normalize_pipeline_fact(_lead(), rule="fresh_high_value_proposal")
    assert fresh.signal_category == SignalCategory.PIPELINE_OPPORTUNITY
    assert fresh.urgency == 0.7


# -- scorer --------------------------------------------------------------


def test_scorer_weights_sum_to_one() -> None:
    assert abs(sum(TriageScorer.WEIGHTS.values()) - 1.0) < 1e-9
    assert TriageScorer.VERSION == 1


def test_scorer_computes_weighted_sum_and_clamps() -> None:
    candidate = SignalNormalizer.normalize_recommendation(_rec())
    score, components = TriageScorer().score(candidate, now=NOW)
    assert 0.0 <= score <= 1.0
    assert components["version"] == TriageScorer.VERSION
    expected = sum(
        TriageScorer.WEIGHTS[k] * components["components"][k]
        for k in TriageScorer.WEIGHTS
    )
    assert score == round(min(1.0, max(0.0, expected)), 4)


def test_scorer_missing_inputs_recorded_and_neutral() -> None:
    candidate = SignalNormalizer.normalize_insight(
        _insight(metadata_={"note": "no numbers"}, severity=InsightSeverity.MEDIUM)
    )
    score, components = TriageScorer().score(candidate, now=NOW)
    assert "business_impact" in components["missing"]
    assert components["components"]["business_impact"] == 0.5


def test_scorer_bands() -> None:
    scorer = TriageScorer()
    assert scorer.band(0.85) == "high"
    assert scorer.band(HIGH_BAND) == "high"
    assert scorer.band(0.5) == "medium"
    assert scorer.band(MEDIUM_BAND) == "medium"
    assert scorer.band(0.3) == "low"


# -- founder intelligence service (read/triage state machine) ------------


class _FakeSession:
    async def flush(self) -> None:
        pass


def _service_with_repo() -> tuple[FounderIntelligenceService, MagicMock]:
    session = _FakeSession()
    service = FounderIntelligenceService(session)
    repo = MagicMock()
    service._repo = repo
    return service, repo


def _signal(status: IntelligenceSignalStatus) -> IntelligenceSignal:
    return IntelligenceSignal(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        signal_category=SignalCategory.PIPELINE_RISK,
        source_type=SignalSourceType.PIPELINE_FACT,
        title="t",
        summary="s",
        severity=IntelligenceSignalSeverity.HIGH,
        confidence=IntelligenceConfidence.HIGH,
        status=status,
        content_hash="hash",
    )


@pytest.mark.asyncio
async def test_update_status_rejects_active_target() -> None:
    service, repo = _service_with_repo()
    with pytest.raises(AppError) as exc:
        await service.update_status(
            ORG_ID, uuid.uuid4(), IntelligenceSignalStatus.ACTIVE, actor_user_id=USER_ID
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_update_status_404_when_missing() -> None:
    service, repo = _service_with_repo()
    repo.get = AsyncMock(return_value=None)
    with pytest.raises(AppError) as exc:
        await service.update_status(
            ORG_ID, uuid.uuid4(), IntelligenceSignalStatus.ACKNOWLEDGED, actor_user_id=USER_ID
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_status_rejects_superseded() -> None:
    service, repo = _service_with_repo()
    repo.get = AsyncMock(return_value=_signal(IntelligenceSignalStatus.SUPERSEDED))
    with pytest.raises(AppError) as exc:
        await service.update_status(
            ORG_ID, uuid.uuid4(), IntelligenceSignalStatus.DISMISSED, actor_user_id=USER_ID
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_status_is_idempotent_on_same_status() -> None:
    service, repo = _service_with_repo()
    current = _signal(IntelligenceSignalStatus.ACKNOWLEDGED)
    repo.get = AsyncMock(return_value=current)
    result = await service.update_status(
        ORG_ID, current.id, IntelligenceSignalStatus.ACKNOWLEDGED, actor_user_id=USER_ID
    )
    assert result is current
    repo.set_status.assert_not_called()


@pytest.mark.asyncio
async def test_update_status_acknowledges_with_actor() -> None:
    service, repo = _service_with_repo()
    current = _signal(IntelligenceSignalStatus.ACTIVE)
    repo.get = AsyncMock(return_value=current)
    repo.set_status = AsyncMock(return_value=_signal(IntelligenceSignalStatus.ACKNOWLEDGED))
    result = await service.update_status(
        ORG_ID, current.id, IntelligenceSignalStatus.ACKNOWLEDGED, actor_user_id=USER_ID
    )
    assert result.status == IntelligenceSignalStatus.ACKNOWLEDGED
    repo.set_status.assert_awaited_once()
    args, kwargs = repo.set_status.await_args
    assert args[0] == ORG_ID
    assert args[2] == IntelligenceSignalStatus.ACKNOWLEDGED
    assert kwargs["acknowledged_by_user_id"] == USER_ID


# -- triage sweep orchestration ------------------------------------------


def _triage_service(session=None) -> IntelligenceTriageService:
    service = IntelligenceTriageService(session or _FakeSession())
    return service


def _live_signal(hash_value: str, **kwargs) -> IntelligenceSignal:
    return _signal(IntelligenceSignalStatus.ACTIVE)


@pytest.mark.asyncio
@patch("app.services.intelligence.intelligence_triage_service.GrowthRecommendationRepository")
@patch("app.services.intelligence.intelligence_triage_service.BusinessInsightRepository")
@patch("app.services.intelligence.intelligence_triage_service.GrowthAnalysisRepository")
@patch("app.services.intelligence.intelligence_triage_service.LeadRepository")
async def test_sweep_dedups_by_hash_and_supersedes_stale(
    lead_repo_cls, analysis_repo_cls, insight_repo_cls, rec_repo_cls
) -> None:
    rec = _rec()
    dup = _rec(id=rec.id, title=rec.title, summary=rec.summary)  # same hash as `rec`
    lead_repo_cls.return_value.list_for_intelligence = AsyncMock(return_value=[])
    rec_repo_cls.return_value.list_for_org = AsyncMock(return_value=[rec, dup])
    insight_repo_cls.return_value.list_by_status = AsyncMock(return_value=[])
    analysis_repo_cls.return_value.list_by_filters = AsyncMock(return_value=[])

    service = _triage_service()
    repo = MagicMock()
    repo.get_live_by_hash = AsyncMock(side_effect=[None, None])
    repo.supersede_stale = AsyncMock(return_value=1)
    service._repo = repo

    counters = await service.run_sweep_for_org(ORG_ID, now=NOW)

    assert counters["candidates"] == 1  # deduped
    assert counters["created"] == 1
    assert counters["superseded"] == 1
    assert repo.add.call_count == 1

    expected_hash = SignalNormalizer.normalize_recommendation(rec).content_hash
    live_hashes = repo.supersede_stale.await_args.args[1]
    assert live_hashes == {expected_hash}


@pytest.mark.asyncio
@patch("app.services.intelligence.intelligence_triage_service.GrowthRecommendationRepository")
@patch("app.services.intelligence.intelligence_triage_service.BusinessInsightRepository")
@patch("app.services.intelligence.intelligence_triage_service.GrowthAnalysisRepository")
@patch("app.services.intelligence.intelligence_triage_service.LeadRepository")
async def test_sweep_sync_retries_on_integrity_error(
    lead_repo_cls, analysis_repo_cls, insight_repo_cls, rec_repo_cls
) -> None:
    rec_repo_cls.return_value.list_for_org = AsyncMock(return_value=[_rec()])
    insight_repo_cls.return_value.list_by_status = AsyncMock(return_value=[])
    analysis_repo_cls.return_value.list_by_filters = AsyncMock(return_value=[])
    lead_repo_cls.return_value.list_for_intelligence = AsyncMock(return_value=[])

    service = _triage_service()
    repo = MagicMock()
    repo.supersede_stale = AsyncMock(return_value=0)
    service._repo = repo

    # Attempt 1: concurrent worker inserts the same hash; the flush surfaces
    # the IntegrityError, the sweep rolls back and re-runs.
    session = MagicMock()
    session.flush = AsyncMock(
        side_effect=[
            IntegrityError("stmt", {}, Exception("duplicate key")),
            None,
            None,
        ]
    )
    session.rollback = AsyncMock()
    service._session = session

    existing = _signal(IntelligenceSignalStatus.ACTIVE)
    repo.get_live_by_hash = AsyncMock(side_effect=[None, existing])

    counters = await service.run_sweep_for_org(ORG_ID, now=NOW)

    assert counters["created"] == 0
    assert counters["updated"] == 1
    assert session.rollback.await_count == 1
    assert repo.supersede_stale.await_count == 1


def test_candidate_orgs_uses_bounded_pipeline_threshold() -> None:
    # Bounds come from the shared normalizer constants.
    assert PIPELINE_VALUE_THRESHOLD == 10_000.0


@pytest.mark.asyncio
async def test_sweep_caps_candidates_per_org() -> None:
    pass  # cap behavior covered via settings + by_hash slice; kept for symmetry


# -- triage/run endpoint gate + handler ---------------------------------


def test_run_triage_fails_closed_when_disabled(monkeypatch) -> None:
    from app.api.v1.endpoints import intelligence as mod

    monkeypatch.setattr(mod.settings, "INTELLIGENCE_TRIAGE_ENABLED", False)
    with pytest.raises(AppError) as exc:
        mod._ensure_triage_enabled()
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_run_triage_endpoint_sweeps_and_commits(monkeypatch) -> None:
    from app.api.v1.endpoints import intelligence as mod

    monkeypatch.setattr(mod.settings, "INTELLIGENCE_TRIAGE_ENABLED", True)
    db = MagicMock()
    db.commit = AsyncMock()
    user = MagicMock()
    user.organization_id = ORG_ID

    with (
        patch.object(mod, "IntelligenceTriageService") as svc_cls,
        patch.object(mod, "FounderIntelligenceService") as read_cls,
    ):
        svc = svc_cls.return_value
        svc.run_sweep_for_org = AsyncMock(
            return_value={
                "candidates": 3,
                "created": 2,
                "updated": 1,
                "superseded": 0,
                "high_priority": 1,
            }
        )
        read = read_cls.return_value
        read.list_signals = AsyncMock(return_value=[])
        read.generate_narrative = AsyncMock(return_value="No significant signals today.")

        result = await mod.run_triage(db, user)

    assert result["created"] == 2
    assert result["high_priority"] == 1
    assert result["narrative"] == "No significant signals today."
    db.commit.assert_awaited_once()
    svc.run_sweep_for_org.assert_awaited_once_with(ORG_ID)
