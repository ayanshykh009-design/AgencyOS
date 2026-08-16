"""Revenue engine — deterministic revenue analysis (M7).

Pure function over a :class:`GrowthContext`. Combines recorded revenue metrics
with won-deal value to produce period revenue, expected value from the open
pipeline (weighted by stage close probability), and a monthly revenue series.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from decimal import Decimal

from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.kpis import open_stage_ids, stage_weight
from app.services.growth_analytics.stats import sum_decimal

_REVENUE_METRIC_TYPES = ("revenue", "mrr", "arr")


def compute_revenue(context: GrowthContext) -> dict:
    """Revenue snapshot for the window."""
    open_ids = open_stage_ids(context)
    max_open_position = max(
        (stage.position for stage in context.stages if stage.lifecycle == "open"),
        default=0,
    )

    won_in_period = [
        lead
        for lead in context.leads
        if lead.won_at and context.period_start <= lead.won_at <= context.period_end
    ]
    won_value_period = sum_decimal(lead.deal_value for lead in won_in_period)

    open_leads = [lead for lead in context.leads if lead.stage_id in open_ids]
    open_value = sum_decimal(lead.deal_value for lead in open_leads)

    weighted_value = sum_decimal(
        lead.deal_value * Decimal(str(stage_weight(position_of(context, lead), max_open_position)))
        for lead in open_leads
        if lead.deal_value is not None
    )

    won_value_total = sum_decimal(lead.deal_value for lead in context.leads if lead.status == "won")
    won_count = sum(1 for lead in context.leads if lead.status == "won")

    monthly: OrderedDict[str, Decimal] = OrderedDict()
    for lead in sorted(
        (lead for lead in won_in_period if lead.won_at and lead.deal_value is not None),
        key=lambda item: item.won_at or datetime.min,
    ):
        won_at = lead.won_at
        deal = lead.deal_value
        assert won_at is not None
        assert deal is not None
        key = won_at.strftime("%Y-%m")
        monthly[key] = monthly.get(key, Decimal("0")) + deal

    revenue_metrics: dict[str, float] = {}
    latest_revenue: Decimal | None = None
    for metric in sorted(context.metrics, key=lambda item: item.period_end):
        if metric.metric_type in _REVENUE_METRIC_TYPES:
            revenue_metrics[metric.metric_type] = float(metric.value)
            latest_revenue = metric.value

    coverage = weighted_value / won_value_period if won_value_period else 0.0

    return {
        "won_revenue_period": float(won_value_period),
        "open_pipeline_value": float(open_value),
        "weighted_pipeline_value": float(weighted_value),
        "expected_value": float(weighted_value),
        "pipeline_coverage": round(float(coverage), 4),
        "average_deal_value": float(won_value_total / won_count) if won_count else 0.0,
        "monthly_revenue": [
            {"month": month, "value": float(value)} for month, value in monthly.items()
        ],
        "revenue_metrics": revenue_metrics,
        "latest_recorded_revenue": float(latest_revenue) if latest_revenue is not None else None,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def position_of(context: GrowthContext, lead) -> int:
    """Stage position of a lead (0 when unknown)."""
    for stage in context.stages:
        if stage.id == lead.stage_id:
            return stage.position
    return 0
