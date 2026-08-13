"""Unit tests for the M7 deterministic growth analytics engines.

The engines are pure functions over a :class:`GrowthContext`; these tests build
small in-memory contexts and assert exact deterministic outputs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.growth_analytics import (
    GrowthContext,
    apply_deltas,
    build_forecast_payload,
    compute_activity,
    compute_bottlenecks,
    compute_conversion,
    compute_forecast,
    compute_funnel,
    compute_health,
    compute_kpis,
    compute_opportunities,
    compute_pipeline,
    compute_revenue,
    compute_trends,
    generate_recommendations,
)
from app.services.growth_analytics.datatypes import (
    ActivityPoint,
    AttemptPoint,
    HealthWeightPoint,
    LeadPoint,
    MetricPoint,
    StagePoint,
    TaskPoint,
)
from app.services.growth_analytics.kpis import compute_kpi_evidence, stage_weight
from app.services.growth_analytics.stats import (
    clamp,
    lerp_band,
    linear_fit,
    mean,
    pct_change,
    sample_stdev,
    sum_decimal,
    wilson_interval,
    zscore,
)

ORG = uuid.UUID("00000000-0000-0000-0000-000000000001")

S1 = uuid.UUID("00000000-0000-0000-0000-000000000101")
S2 = uuid.UUID("00000000-0000-0000-0000-000000000102")
S3 = uuid.UUID("00000000-0000-0000-0000-000000000103")

PERIOD_START = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
PERIOD_END = datetime(2026, 1, 31, tzinfo=UTC).replace(tzinfo=None)


def _stage(*, id_: uuid.UUID, name: str, position: int, lifecycle: str) -> StagePoint:
    return StagePoint(id=id_, name=name, position=position, lifecycle=lifecycle)


def _lead(
    *,
    id_: uuid.UUID,
    status: str,
    stage_id: uuid.UUID | None,
    deal_value: str | None = None,
    won_at: datetime | None = None,
    lost_at: datetime | None = None,
    created_at: datetime | None = None,
    name: str = "Acme Corp",
) -> LeadPoint:
    return LeadPoint(
        id=id_,
        status=status,
        stage_id=stage_id,
        deal_value=Decimal(deal_value) if deal_value is not None else None,
        won_at=won_at,
        lost_at=lost_at,
        created_at=created_at,
        owner_user_id=None,
        name=name,
    )


def _base_context() -> GrowthContext:
    return GrowthContext(
        organization_id=ORG,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        stages=[
            _stage(id_=S1, name="Discovery", position=1, lifecycle="open"),
            _stage(id_=S2, name="Proposal", position=2, lifecycle="open"),
            _stage(id_=S3, name="Closed Won", position=3, lifecycle="won"),
        ],
    )


# -- stats ------------------------------------------------------------


def test_linear_fit_slope_intercept() -> None:
    slope, intercept, r2, residuals = linear_fit([0.0, 1.0, 2.0], [1.0, 3.0, 5.0])
    assert slope == 2.0
    assert intercept == 1.0
    assert r2 == 1.0
    assert residuals == [0.0, 0.0, 0.0]


def test_linear_fit_single_point_degenerates() -> None:
    slope, intercept, r2, residuals = linear_fit([1.0], [5.0])
    assert slope == 0.0
    assert intercept == 5.0
    assert r2 == 0.0
    assert residuals == []


def test_stats_helpers() -> None:
    assert mean([1.0, 2.0, 3.0]) == 2.0
    assert mean([]) == 0.0
    assert sample_stdev([2.0, 4.0, 6.0]) == 2.0
    assert sample_stdev([1.0]) == 0.0
    assert zscore(4.0, 2.0, 2.0) == 1.0
    assert zscore(4.0, 2.0, 0.0) == 0.0
    assert clamp(5.0, 0.0, 3.0) == 3.0
    assert pct_change(10.0, 12.0) == 0.2
    assert pct_change(0.0, 5.0) == 0.0
    assert lerp_band(50.0, 0.0, 100.0) == 50.0
    assert lerp_band(-1.0, 0.0, 100.0) == 0.0
    assert lerp_band(200.0, 0.0, 100.0) == 100.0


def test_sum_decimal_skips_none() -> None:
    assert sum_decimal([Decimal("1.5"), 2, None, 3.5]) == Decimal("7.0")


def test_wilson_interval() -> None:
    lower, upper = wilson_interval(90, 100)
    assert 0.8 < lower < 1.0
    assert 0.8 < upper <= 1.0
    assert wilson_interval(0, 0) == (0.0, 0.0)


# -- kpis -------------------------------------------------------------


def test_stage_weight_ramp() -> None:
    assert stage_weight(0, 2) == 0.15
    assert stage_weight(2, 2) == 1.0
    assert stage_weight(1, 0) == 0.5


def test_compute_kpis_basic() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(
            id_=uuid.uuid4(),
            status="new",
            stage_id=S1,
            deal_value="1000",
            created_at=PERIOD_START + timedelta(days=2),
        ),
        _lead(
            id_=uuid.uuid4(),
            status="won",
            stage_id=None,
            deal_value="500",
            won_at=PERIOD_START,
            created_at=PERIOD_START - timedelta(days=10),
        ),
        _lead(
            id_=uuid.uuid4(),
            status="lost",
            stage_id=None,
            lost_at=PERIOD_START,
            created_at=PERIOD_START - timedelta(days=5),
        ),
        _lead(
            id_=uuid.uuid4(),
            status="new",
            stage_id=None,
            created_at=PERIOD_START - timedelta(days=60),
        ),
    ]
    kpis = compute_kpis(ctx)

    assert kpis["totals"]["total_leads"] == 4
    assert kpis["totals"]["won_leads"] == 1
    assert kpis["totals"]["lost_leads"] == 1
    assert kpis["totals"]["active_leads"] == 1
    assert kpis["totals"]["unassigned_leads"] == 4
    assert kpis["performance"]["win_rate"] == 0.5
    assert kpis["performance"]["conversion_rate"] == 0.25
    assert kpis["performance"]["average_deal_value"] == 500.0
    assert kpis["period"]["new_leads"] == 1


def test_compute_kpi_evidence_rows() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="won", stage_id=None, deal_value="100"),
    ]
    kpis = compute_kpis(ctx)
    evidence = compute_kpi_evidence(ctx, kpis)
    assert len(evidence) == 5
    assert evidence[0]["kpi"] == "win_rate"
    assert evidence[0]["value"] == 1.0


# -- pipeline ---------------------------------------------------------


def test_compute_pipeline_weights_by_position() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1, deal_value="1000"),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S2, deal_value="1000"),
    ]
    pipeline = compute_pipeline(ctx)

    assert pipeline["total_open"] == 2
    assert pipeline["open_value"] == 2000.0
    by_stage = {row["stage_id"]: row for row in pipeline["by_stage"]}
    assert by_stage[str(S1)]["weighted_value"] == 1000.0 * stage_weight(1, 2)
    assert by_stage[str(S2)]["weighted_value"] == 1000.0 * stage_weight(2, 2)
    assert pipeline["weighted_value"] == round(
        1000.0 * stage_weight(1, 2) + 1000.0 * stage_weight(2, 2), 2
    )
    assert pipeline["expected_value"] == pipeline["weighted_value"]


# -- funnel -----------------------------------------------------------


def test_compute_funnel_snapshot_approximation() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S2),
        _lead(id_=uuid.uuid4(), status="won", stage_id=None),
        _lead(id_=uuid.uuid4(), status="lost", stage_id=None),
    ]
    funnel = compute_funnel(ctx)

    assert funnel["entry"] == 4
    assert funnel["exit_won"] == 1
    assert funnel["exit_lost"] == 1
    rows = funnel["funnel"]
    assert [row["count"] for row in rows] == [1, 1]
    assert rows[1]["entered"] == 2
    assert "approximation" in funnel["note"]


# -- conversion --------------------------------------------------------


def test_compute_conversion_rates() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S2),
        _lead(id_=uuid.uuid4(), status="won", stage_id=None),
        _lead(id_=uuid.uuid4(), status="lost", stage_id=None),
    ]
    conversion = compute_conversion(ctx)

    assert conversion["win_rate"] == 0.5
    assert conversion["loss_rate"] == 0.5
    assert conversion["overall_conversion"] == 0.25
    assert len(conversion["stage_to_stage"]) == 1
    assert conversion["stage_to_stage"][0]["conversion"] == 1.0
    assert conversion["meeting_count"] == 0
    assert conversion["proposal_count"] == 1


# -- revenue ----------------------------------------------------------


def test_compute_revenue_combines_metrics_and_wins() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(
            id_=uuid.uuid4(),
            status="won",
            stage_id=None,
            deal_value="500",
            won_at=PERIOD_START + timedelta(days=1),
        ),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1, deal_value="1000"),
    ]
    ctx.metrics = [
        MetricPoint(
            metric_type="revenue",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            value=Decimal("2000"),
        )
    ]
    revenue = compute_revenue(ctx)

    assert revenue["won_revenue_period"] == 500.0
    assert revenue["open_pipeline_value"] == 1000.0
    assert revenue["weighted_pipeline_value"] == round(1000.0 * stage_weight(1, 2), 2)
    assert revenue["revenue_metrics"] == {"revenue": 2000.0}
    assert revenue["latest_recorded_revenue"] == 2000.0
    assert revenue["monthly_revenue"] == [{"month": "2026-01", "value": 500.0}]


# -- activity ---------------------------------------------------------


def test_compute_activity_totals_and_channels() -> None:
    ctx = _base_context()
    ctx.attempts = [
        AttemptPoint(status="sent", channel="email", created_at=PERIOD_START),
        AttemptPoint(status="replied", channel="email", created_at=PERIOD_START),
        AttemptPoint(status="failed", channel="linkedin", created_at=PERIOD_START),
    ]
    ctx.tasks = [
        TaskPoint(status="done", created_at=PERIOD_START, completed_at=PERIOD_END),
        TaskPoint(status="open", created_at=PERIOD_START, completed_at=None),
    ]
    ctx.activity = [
        ActivityPoint(event_type="call_logged", created_at=PERIOD_START),
        ActivityPoint(event_type="call_logged", created_at=PERIOD_START),
        ActivityPoint(event_type="note_added", created_at=PERIOD_START),
    ]
    activity = compute_activity(ctx)

    outreach = activity["outreach"]
    assert outreach["total_attempts"] == 3
    assert outreach["sent"] == 1
    assert outreach["replied"] == 1
    assert outreach["failed"] == 1
    assert outreach["reply_rate"] == 1.0
    channels = {row["channel"]: row for row in outreach["by_channel"]}
    assert channels["email"]["reply_rate"] == 1.0
    assert activity["tasks"] == {"created": 2, "completed": 1, "open": 1, "completion_rate": 0.5}
    assert activity["events"]["total"] == 3
    assert activity["events"]["top"][0]["event_type"] == "call_logged"


# -- bottleneck -------------------------------------------------------


def test_compute_bottlenecks_detects_dropoff() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S2),
    ]
    bottlenecks = compute_bottlenecks(ctx)

    assert len(bottlenecks["bottlenecks"]) == 1
    primary = bottlenecks["primary"]
    assert primary["stage"] == "Proposal"
    assert primary["dropoff"] == 1
    assert primary["dropoff_ratio"] == 0.5
    assert primary["severity"] == "high"


def test_compute_bottlenecks_empty() -> None:
    bottlenecks = compute_bottlenecks(_base_context())
    assert bottlenecks["bottlenecks"] == []
    assert bottlenecks["primary"] is None


# -- opportunities ----------------------------------------------------


def test_compute_opportunities_uses_lead_name() -> None:
    ctx = _base_context()
    lead = _lead(id_=uuid.uuid4(), status="new", stage_id=S2, deal_value="2000", name="Jane Doe")
    won = _lead(
        id_=uuid.uuid4(),
        status="won",
        stage_id=None,
        deal_value="900",
        won_at=PERIOD_START,
        name="Won Inc",
    )
    ctx.leads = [lead, won]
    opportunities = compute_opportunities(ctx)

    assert opportunities["top_opportunities"][0]["name"] == "Jane Doe"
    assert opportunities["top_opportunities"][0]["expected_value"] == round(
        2000.0 * stage_weight(2, 2), 2
    )
    assert opportunities["recent_won"][0]["name"] == "Won Inc"


# -- trends -----------------------------------------------------------


def test_compute_trends_slope_and_label() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1, created_at=datetime(2026, 1, 5)),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1, created_at=datetime(2026, 2, 5)),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1, created_at=datetime(2026, 2, 9)),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1, created_at=datetime(2026, 3, 5)),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1, created_at=datetime(2026, 3, 9)),
        _lead(id_=uuid.uuid4(), status="new", stage_id=S1, created_at=datetime(2026, 3, 13)),
    ]
    ctx.metrics = [
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
            value=Decimal("1500"),
        ),
    ]
    trends = compute_trends(ctx)

    assert trends["leads"]["count"] == 3
    assert [item["count"] for item in trends["leads"]["series"]] == [1, 2, 3]
    assert trends["leads"]["trend"] == "up"
    assert trends["revenue"]["count"] == 2
    assert trends["revenue"]["trend"] == "up"
    assert trends["revenue"]["growth_pct"] == 0.5


# -- forecast ---------------------------------------------------------


def test_compute_forecast_linear_trend() -> None:
    ctx = _base_context()
    ctx.metrics = [
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
    ]
    result = compute_forecast(ctx, "linear_trend")
    assert result.method == "linear_trend"
    assert result.point_estimate == 1400.0
    assert result.errors == []


def test_compute_forecast_moving_average() -> None:
    ctx = _base_context()
    ctx.metrics = [
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
    ]
    result = compute_forecast(ctx, "moving_average")
    assert result.method == "moving_average"
    assert result.point_estimate == 1100.0


def test_compute_forecast_pipeline_weighted() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="new", stage_id=S2, deal_value="1000"),
    ]
    result = compute_forecast(ctx, "pipeline_weighted")
    assert result.method == "pipeline_weighted"
    assert result.point_estimate == round(1000.0 * stage_weight(2, 2), 2)


def test_compute_forecast_seasonal_naive_and_band() -> None:
    ctx = _base_context()
    ctx.metrics = [
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
    ]
    result = compute_forecast(ctx, "seasonal_naive")
    assert result.method == "seasonal_naive"
    assert result.point_estimate == 1200.0
    assert result.lower_bound <= result.point_estimate <= result.upper_bound
    assert len(result.series) == 3
    assert result.series[-1]["period"] == "next"


def test_compute_forecast_unsupported_method_falls_back() -> None:
    ctx = _base_context()
    ctx.metrics = [
        MetricPoint(
            metric_type="revenue",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            value=Decimal("1000"),
        ),
        MetricPoint(
            metric_type="revenue",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            value=Decimal("1200"),
        ),
    ]
    result = compute_forecast(ctx, "bogus")
    assert result.method == "linear_trend"
    assert result.errors and "unsupported" in result.errors[0]


def test_build_forecast_payload_is_json_safe() -> None:
    ctx = _base_context()
    ctx.metrics = [
        MetricPoint(
            metric_type="revenue",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            value=Decimal("1000"),
        ),
    ]
    payload = build_forecast_payload(ctx, "seasonal_naive")
    assert set(payload) == {
        "method",
        "point_estimate",
        "lower_bound",
        "upper_bound",
        "series",
        "errors",
        "generated_at",
    }


# -- scenario ---------------------------------------------------------


def test_apply_deltas_projects_revenue() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="won", stage_id=None, deal_value="100"),
        _lead(id_=uuid.uuid4(), status="lost", stage_id=None),
    ]
    result = apply_deltas(
        ctx,
        {
            "new_leads_delta": 2.0,
            "conversion_delta": 1.0,
            "win_rate_delta": 1.0,
            "avg_deal_value_delta": 1.0,
        },
    )

    assert result["baseline"]["leads"] == 2
    assert result["baseline"]["win_rate"] == 0.5
    assert result["projected"]["leads"] == 4.0
    assert result["projected"]["win_rate"] == 0.5
    assert result["projected"]["closed_deals"] == 1.0
    assert result["projected"]["revenue"] == 100.0


def test_apply_deltas_defaults_no_change() -> None:
    ctx = _base_context()
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="won", stage_id=None, deal_value="100"),
    ]
    result = apply_deltas(ctx, {})
    assert result["params"] == {
        "new_leads_delta": 1.0,
        "conversion_delta": 1.0,
        "win_rate_delta": 1.0,
        "avg_deal_value_delta": 1.0,
    }
    assert result["projected"]["revenue"] == 100.0


# -- health -----------------------------------------------------------


def test_compute_health_default_weights() -> None:
    ctx = _base_context()
    ctx.metrics = [
        MetricPoint(
            metric_type="revenue",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            value=Decimal("1000"),
        ),
    ]
    ctx.leads = [
        _lead(id_=uuid.uuid4(), status="new", stage_id=S2, deal_value="1000"),
        _lead(id_=uuid.uuid4(), status="won", stage_id=None, deal_value="100"),
        _lead(id_=uuid.uuid4(), status="lost", stage_id=None),
    ]
    health = compute_health(ctx)

    assert 0 <= health["score"] <= 100
    assert set(health["dimensions"]) == {
        "pipeline_health",
        "activity_level",
        "conversion_health",
        "revenue_health",
        "coverage_health",
    }
    assert health["weights"] == {
        "pipeline_health": 0.25,
        "activity_level": 0.2,
        "conversion_health": 0.2,
        "revenue_health": 0.25,
        "coverage_health": 0.1,
    }


def test_compute_health_uses_custom_weights() -> None:
    ctx = _base_context()
    ctx.health_weights = [
        HealthWeightPoint(dimension="pipeline_health", weight=1.0, position=0),
    ]
    health = compute_health(ctx)
    assert health["weights"]["pipeline_health"] == 1.0


# -- recommendations --------------------------------------------------


def test_generate_recommendations_empty_maintain() -> None:
    results = {
        "bottlenecks": {"bottlenecks": []},
        "conversion": {"win_rate": 0.5},
        "activity": {"outreach": {"sent": 10, "reply_rate": 0.3}},
        "trends": {"revenue": {"trend": "up"}, "leads": {"trend": "up"}},
        "health": {"score": 70.0},
        "revenue": {"pipeline_coverage": 5.0},
    }
    recommendations = generate_recommendations(results)
    assert len(recommendations) == 1
    assert recommendations[0]["type"] == "maintain"
    assert recommendations[0]["status"] == "active"


def test_generate_recommendations_low_win_rate() -> None:
    results = {"conversion": {"win_rate": 0.1}}
    recommendations = generate_recommendations(results)
    assert any(
        item["type"] == "conversion" and item["metric_target"] == "win_rate"
        for item in recommendations
    )


def test_generate_recommendations_bottleneck_and_health() -> None:
    results = {
        "bottlenecks": {
            "bottlenecks": [
                {
                    "stage": "Proposal",
                    "stage_id": str(S2),
                    "entered": 10,
                    "dropoff": 8,
                    "dropoff_ratio": 0.8,
                    "severity": "high",
                }
            ]
        },
        "health": {"score": 25.0},
        "revenue": {"pipeline_coverage": 1.0},
        "activity": {"outreach": {"sent": 0}},
        "trends": {"revenue": {"trend": "down", "slope": -0.2, "count": 3}},
    }
    recommendations = generate_recommendations(results)
    types = {item["type"] for item in recommendations}
    assert "bottleneck" in types
    assert "health" in types
    assert "pipeline" in types
    assert "activity" in types
    assert "trend" in types
