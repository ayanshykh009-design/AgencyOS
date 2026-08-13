"""KPI engine — deterministic key performance indicators (M7).

Pure function over a :class:`GrowthContext`. Returns JSON-safe KPIs: pipeline
totals, win/loss performance, conversion, average deal size, sales-cycle
length, and period-scoped new/won/lost counts plus outreach reply rate.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.stats import (
    sum_decimal,
    to_float,
)

_WON = "won"
_LOST = "lost"
_REVENUE_METRIC_TYPES = ("revenue", "mrr", "arr")
_SENT_STATUSES = ("sent", "delivered", "manually_sent")
_REPLIED_STATUSES = ("replied",)


def open_stage_ids(context: GrowthContext) -> set:
    """Ids of pipeline stages in the open (active) lifecycle bucket."""
    return {stage.id for stage in context.stages if stage.lifecycle == "open"}


def stage_weight(position: int, max_position: int) -> float:
    """Close probability weight for a stage: ramp 0.15 -> 1.0 by position.

    The last open stage before a terminal (won) state is treated as the most
    likely to close; the first as the least.
    """
    if max_position <= 0:
        return 0.5
    return 0.15 + 0.85 * (position / max_position)


def compute_kpis(context: GrowthContext) -> dict:
    """Compute the KPI snapshot for the context window."""
    open_ids = open_stage_ids(context)
    max_open_position = max(
        (s.position for s in context.stages if s.lifecycle == "open"), default=0
    )

    open_leads = [lead for lead in context.leads if lead.stage_id in open_ids]
    won_leads = [lead for lead in context.leads if lead.status == _WON]
    lost_leads = [lead for lead in context.leads if lead.status == _LOST]

    open_value = sum_decimal(lead.deal_value for lead in open_leads)
    weighted_value = Decimal("0")
    for lead in open_leads:
        if lead.deal_value is None:
            continue
        position = 0
        for stage in context.stages:
            if stage.id == lead.stage_id:
                position = stage.position
                break
        weighted_value += lead.deal_value * Decimal(str(stage_weight(position, max_open_position)))

    won_value = sum_decimal(lead.deal_value for lead in won_leads)
    won_count = len(won_leads)
    lost_count = len(lost_leads)
    decided = won_count + lost_count

    cycle_days: list[float] = []
    for lead in won_leads:
        if lead.won_at and lead.created_at:
            days = (lead.won_at - lead.created_at).total_seconds() / 86400.0
            if days >= 0:
                cycle_days.append(days)

    new_in_period = sum(
        1
        for lead in context.leads
        if lead.created_at and context.period_start <= lead.created_at <= context.period_end
    )
    won_in_period = sum(
        1
        for lead in context.leads
        if lead.won_at and context.period_start <= lead.won_at <= context.period_end
    )
    lost_in_period = sum(
        1
        for lead in context.leads
        if lead.lost_at and context.period_start <= lead.lost_at <= context.period_end
    )

    sent = sum(1 for attempt in context.attempts if attempt.status in _SENT_STATUSES)
    replied = sum(1 for attempt in context.attempts if attempt.status in _REPLIED_STATUSES)
    reply_rate = replied / sent if sent else 0.0

    revenue_metrics: dict[str, Decimal] = {}
    for metric in context.metrics:
        if metric.metric_type in _REVENUE_METRIC_TYPES:
            revenue_metrics[metric.metric_type] = metric.value

    total_leads = len(context.leads)
    conversion_rate = won_count / total_leads if total_leads else 0.0
    win_rate = won_count / decided if decided else 0.0
    average_deal_value = won_value / won_count if won_count else Decimal("0")
    average_cycle_days = round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else 0.0

    return {
        "window": {
            "period_start": context.period_start.isoformat(),
            "period_end": context.period_end.isoformat(),
        },
        "totals": {
            "total_leads": total_leads,
            "active_leads": len(open_leads),
            "won_leads": won_count,
            "lost_leads": lost_count,
            "unassigned_leads": sum(1 for lead in context.leads if lead.owner_user_id is None),
        },
        "pipeline_value": {
            "open_pipeline_value": float(open_value),
            "weighted_pipeline_value": float(weighted_value),
            "won_value": float(won_value),
        },
        "performance": {
            "win_rate": round(win_rate, 4),
            "conversion_rate": round(conversion_rate, 4),
            "average_deal_value": float(average_deal_value),
            "average_cycle_days": average_cycle_days,
        },
        "period": {
            "new_leads": new_in_period,
            "won_leads": won_in_period,
            "lost_leads": lost_in_period,
            "sent_attempts": sent,
            "replies": replied,
            "reply_rate": round(reply_rate, 4),
        },
        "revenue_metrics": {k: float(v) for k, v in revenue_metrics.items()},
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def compute_kpi_evidence(context: GrowthContext, kpis: dict) -> list[dict]:
    """Human-checkable evidence rows backing the KPI snapshot."""
    decided = kpis["totals"]["won_leads"] + kpis["totals"]["lost_leads"]
    return [
        {
            "kpi": "win_rate",
            "value": kpis["performance"]["win_rate"],
            "detail": f"{kpis['totals']['won_leads']} won of {decided} decided leads",
        },
        {
            "kpi": "conversion_rate",
            "value": kpis["performance"]["conversion_rate"],
            "detail": f"{kpis['totals']['won_leads']} won of {kpis['totals']['total_leads']} leads",
        },
        {
            "kpi": "weighted_pipeline_value",
            "value": kpis["pipeline_value"]["weighted_pipeline_value"],
            "detail": "Weighted by stage close probability",
        },
        {
            "kpi": "reply_rate",
            "value": kpis["period"]["reply_rate"],
            "detail": (
                f"{kpis['period']['replies']} replies of "
                f"{kpis['period']['sent_attempts']} sent attempts"
            ),
        },
        {
            "kpi": "new_leads",
            "value": kpis["period"]["new_leads"],
            "detail": (
                f"Leads created between {kpis['window']['period_start']} and "
                f"{kpis['window']['period_end']}"
            ),
        },
    ]


def to_decimal(value: Decimal | float | None) -> Decimal:
    """Coerce a numeric to Decimal for engine math."""
    return Decimal(str(to_float(value)))
