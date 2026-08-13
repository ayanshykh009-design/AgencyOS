"""Unit tests for the M7 growth analytics service and growth agent executor.

The service is exercised with a stubbed session: the context repository's
``build`` is replaced with an in-memory context and persistence repositories
are replaced with capture lists. ``commit_with_retry`` is neutralized.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.agents.executors.base import ExecutorContext
from app.agents.executors.growth_executor import GrowthAgentExecutor
from app.core.config import settings
from app.core.errors import AppError
from app.models.enums import GrowthAnalysisType, RecommendationStatus
from app.services.growth_analytics import GrowthContext
from app.services.growth_analytics.datatypes import (
    MetricPoint,
    StagePoint,
)
from app.services.growth_analytics.health import DEFAULT_WEIGHTS
from app.services.growth_analytics_service import GrowthAnalyticsService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
S1 = uuid.UUID("00000000-0000-0000-0000-000000000101")
PERIOD_START = datetime(2026, 1, 1)
PERIOD_END = datetime(2026, 1, 31)


class FakeSession:
    """Minimal AsyncSession stand-in: records adds and tracks commits."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def refresh(self, instance: Any) -> None:
        pass


def _context() -> GrowthContext:
    return GrowthContext(
        organization_id=ORG_ID,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        stages=[StagePoint(id=S1, name="Discovery", position=1, lifecycle="open")],
        metrics=[
            MetricPoint(
                metric_type="revenue",
                period_start=PERIOD_START,
                period_end=datetime(2026, 1, 31),
                value=Decimal("1000"),
            ),
            MetricPoint(
                metric_type="revenue",
                period_start=PERIOD_START,
                period_end=datetime(2026, 2, 28),
                value=Decimal("1200"),
            ),
        ],
    )


async def _service(session: FakeSession, monkeypatch: pytest.MonkeyPatch) -> GrowthAnalyticsService:
    service = GrowthAnalyticsService(session)
    monkeypatch.setattr(service._context, "build", lambda *a, **k: _coro(_context()))
    monkeypatch.setattr(
        "app.services.growth_analytics_service.commit_with_retry", _commit_noop
    )
    return service


async def _commit_noop(session: Any) -> None:
    await session.commit()


def _coro(value: Any) -> Any:
    async def _inner() -> Any:
        return value

    return _inner()


# -- analyses ---------------------------------------------------------


@pytest.mark.asyncio
async def test_run_analysis_persists_completed_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)

    analysis = await service.run_analysis(
        ORG_ID,
        analysis_type=GrowthAnalysisType.KPIS,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    assert analysis.status.value == "completed"
    assert analysis.summary.startswith("KPI snapshot")
    assert analysis.details["totals"]["total_leads"] == 0
    assert len(analysis.evidence) == 5
    assert analysis.metrics_used == ["revenue"]
    assert session.added and session.added[0] is analysis
    assert session.commits == 1


@pytest.mark.asyncio
async def test_run_analysis_persists_failed_snapshot_on_engine_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("engine exploded")

    monkeypatch.setattr(service, "_run_engine", _boom)
    analysis = await service.run_analysis(
        ORG_ID,
        analysis_type=GrowthAnalysisType.HEALTH,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    assert analysis.status.value == "failed"
    assert analysis.error == "engine exploded"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_run_analysis_rejects_inverted_period(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)

    with pytest.raises(AppError) as exc:
        await service.run_analysis(
            ORG_ID,
            analysis_type=GrowthAnalysisType.KPIS,
            period_start=PERIOD_END,
            period_end=PERIOD_START,
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "growth_analysis.period_invalid"


@pytest.mark.asyncio
async def test_run_full_analysis_persists_all_types_and_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)

    analyses = await service.run_full_analysis(
        ORG_ID, period_start=PERIOD_START, period_end=PERIOD_END
    )

    assert len(analyses) == len(list(GrowthAnalysisType))
    assert all(analysis.status.value == "completed" for analysis in analyses)
    health = next(a for a in analyses if a.analysis_type == GrowthAnalysisType.HEALTH)
    assert health.health_score is not None
    recommendations = [
        item for item in session.added if item.__class__.__name__ == "GrowthRecommendation"
    ]
    assert recommendations
    assert all(rec.source_analysis_id == health.id for rec in recommendations)


@pytest.mark.asyncio
async def test_preview_analysis_does_not_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)

    preview = await service.preview_analysis(
        ORG_ID,
        analysis_type=GrowthAnalysisType.PIPELINE,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    assert preview["analysis_type"] == "pipeline"
    assert "total_open" in preview["details"]
    assert session.added == []
    assert session.commits == 0


# -- recommendations --------------------------------------------------


@pytest.mark.asyncio
async def test_update_recommendation_changes_triage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.growth_recommendation import GrowthRecommendation

    session = FakeSession()
    service = await _service(session, monkeypatch)
    rec = GrowthRecommendation(
        organization_id=ORG_ID,
        recommendation_type="maintain",
        priority="low",
        confidence="low",
        status="active",
        title="t",
        summary="s",
        action_type="maintain",
        action_payload={},
        evidence=[],
    )
    monkeypatch.setattr(service._recommendations, "get_or_404", lambda *a, **k: _coro(rec))

    updated = await service.update_recommendation(
        ORG_ID, uuid.uuid4(), status=RecommendationStatus.ACKNOWLEDGED
    )
    assert updated.status is RecommendationStatus.ACKNOWLEDGED


# -- scenarios --------------------------------------------------------


@pytest.mark.asyncio
async def test_create_scenario_persists_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)

    scenario = await service.create_scenario(
        ORG_ID,
        name="Double leads",
        description="What if we 2x lead flow?",
        assumption_deltas={"new_leads_delta": 2.0},
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    assert scenario.name == "Double leads"
    assert scenario.result["params"]["new_leads_delta"] == 2.0
    assert session.commits == 1


@pytest.mark.asyncio
async def test_delete_scenario_missing_raises_404(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)
    monkeypatch.setattr(service._scenarios, "delete", lambda *a, **k: _coro(False))

    with pytest.raises(AppError) as exc:
        await service.delete_scenario(ORG_ID, uuid.uuid4())
    assert exc.value.status_code == 404
    assert exc.value.code == "growth_scenario.not_found"


# -- health weights ---------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_health_weights_bumps_version(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.growth_health_weight import GrowthHealthWeight

    session = FakeSession()
    service = await _service(session, monkeypatch)

    active = GrowthHealthWeight(
        organization_id=ORG_ID, version=2, weights={**DEFAULT_WEIGHTS}, is_active=True
    )
    monkeypatch.setattr(service._health_weights, "active", lambda *a, **k: _coro(active))
    deactivated: list[Any] = []
    monkeypatch.setattr(
        service._health_weights, "deactivate_all", lambda *a, **k: _deactivate(deactivated)
    )

    row = await service.upsert_health_weights(
        ORG_ID, weights={"pipeline_health": 0.5, "activity_level": 0.5}
    )

    assert row.version == 3
    assert row.is_active is True
    assert deactivated == [ORG_ID]


async def _deactivate(deactivated: list[Any]) -> None:
    deactivated.append(ORG_ID)


# -- forecasts --------------------------------------------------------


@pytest.mark.asyncio
async def test_run_forecast_persists_row(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)

    forecast = await service.run_forecast(
        ORG_ID,
        method="moving_average",
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        horizon_start=PERIOD_END + timedelta(days=1),
        horizon_end=PERIOD_END + timedelta(days=31),
    )

    assert forecast.method == "moving_average"
    assert forecast.point_estimate == Decimal("1100")
    assert forecast.total_value == Decimal("1100")
    assert forecast.series[-1]["period"] == "next"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_run_forecast_rejects_unknown_method(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    service = await _service(session, monkeypatch)

    with pytest.raises(AppError) as exc:
        await service.run_forecast(
            ORG_ID,
            method="bogus",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            horizon_start=PERIOD_END,
            horizon_end=PERIOD_END + timedelta(days=31),
        )
    assert exc.value.status_code == 422
    assert exc.value.code == "growth_forecast.invalid_method"


# -- executor ---------------------------------------------------------


def _ctx(*, analysis_type: str | None = None, period_start: str | None = None) -> ExecutorContext:
    return ExecutorContext(
        session=FakeSession(),
        organization_id=ORG_ID,
        run_id=uuid.uuid4(),
        goal="run_growth_analysis",
        input={
            **({"analysis_type": analysis_type} if analysis_type is not None else {}),
            **({"period_start": period_start} if period_start is not None else {}),
        },
    )


@pytest.mark.asyncio
async def test_growth_executor_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GROWTH_AGENT_ENABLED", False)
    result = await GrowthAgentExecutor().execute(_ctx(analysis_type="full"))
    assert result.success is False
    assert "disabled" in (result.error or "")


@pytest.mark.asyncio
async def test_growth_executor_full_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.enums import GrowthAnalysisStatus
    from app.models.growth_analysis import GrowthAnalysis

    monkeypatch.setattr(settings, "GROWTH_AGENT_ENABLED", True)
    analyses = [
        GrowthAnalysis(
            organization_id=ORG_ID,
            analysis_type=analysis_type,
            status=GrowthAnalysisStatus.COMPLETED,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            summary="s",
            details={},
            evidence=[],
            weights={},
            metrics_used=[],
            generated_by="growth_agent",
        )
        for analysis_type in list(GrowthAnalysisType)
    ]

    class FakeService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def run_full_analysis(self, *args: Any, **kwargs: Any) -> list[GrowthAnalysis]:
            return analyses

        async def list_recommendations(self, *args: Any, **kwargs: Any) -> list[Any]:
            return [1, 2]

    monkeypatch.setattr(
        "app.agents.executors.growth_executor.GrowthAnalyticsService", FakeService
    )
    result = await GrowthAgentExecutor().execute(_ctx(analysis_type="full"))
    assert result.success is True
    assert len(result.output["ran_analysis_types"]) == len(list(GrowthAnalysisType))
    assert result.output["recommendations"] == 2


@pytest.mark.asyncio
async def test_growth_executor_single_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.enums import GrowthAnalysisStatus
    from app.models.growth_analysis import GrowthAnalysis

    monkeypatch.setattr(settings, "GROWTH_AGENT_ENABLED", True)
    analysis = GrowthAnalysis(
        organization_id=ORG_ID,
        analysis_type=GrowthAnalysisType.REVENUE,
        status=GrowthAnalysisStatus.COMPLETED,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        summary="Revenue snapshot",
        details={},
        evidence=[],
        weights={},
        metrics_used=[],
        generated_by="growth_agent",
        generated_at=PERIOD_START,
    )

    class FakeService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def run_analysis(self, *args: Any, **kwargs: Any) -> GrowthAnalysis:
            return analysis

    monkeypatch.setattr(
        "app.agents.executors.growth_executor.GrowthAnalyticsService", FakeService
    )
    result = await GrowthAgentExecutor().execute(_ctx(analysis_type="revenue"))
    assert result.success is True
    assert result.output["analysis_type"] == "revenue"
    assert result.output["status"] == "completed"


@pytest.mark.asyncio
async def test_growth_executor_unknown_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GROWTH_AGENT_ENABLED", True)
    result = await GrowthAgentExecutor().execute(_ctx(analysis_type="bogus"))
    assert result.success is False
    assert "unknown analysis_type" in (result.error or "")


@pytest.mark.asyncio
async def test_growth_executor_parses_period_input(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.enums import GrowthAnalysisStatus
    from app.models.growth_analysis import GrowthAnalysis

    monkeypatch.setattr(settings, "GROWTH_AGENT_ENABLED", True)
    analysis = GrowthAnalysis(
        organization_id=ORG_ID,
        analysis_type=GrowthAnalysisType.KPIS,
        status=GrowthAnalysisStatus.COMPLETED,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        summary="s",
        details={},
        evidence=[],
        weights={},
        metrics_used=[],
        generated_by="growth_agent",
        generated_at=PERIOD_START,
    )
    captured: dict[str, Any] = {}

    class FakeService:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def run_analysis(self, *args: Any, **kwargs: Any) -> GrowthAnalysis:
            captured.update(kwargs)
            return analysis

    monkeypatch.setattr(
        "app.agents.executors.growth_executor.GrowthAnalyticsService", FakeService
    )
    result = await GrowthAgentExecutor().execute(
        _ctx(analysis_type="kpis", period_start="2026-01-01T00:00:00Z")
    )
    assert result.success is True
    assert captured["period_start"] == datetime(2026, 1, 1)
