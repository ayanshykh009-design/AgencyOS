"""Health engine — deterministic growth health scoring (M7).

Pure function over a :class:`GrowthContext`. Computes dimension scores in
[0, 1] for pipeline, activity, conversion, revenue, and coverage, then blends
them with per-org weights (from ``growth_health_weights``) into a composite
growth health score (0-100). Each score carries an explanatory label.
"""

from __future__ import annotations

from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.kpis import open_stage_ids, stage_weight
from app.services.growth_analytics.stats import mean

DEFAULT_WEIGHTS = {
    "pipeline_health": 0.25,
    "activity_level": 0.20,
    "conversion_health": 0.20,
    "revenue_health": 0.25,
    "coverage_health": 0.10,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _effective_weights(context: GrowthContext) -> dict[str, float]:
    weights: dict[str, float] = {**DEFAULT_WEIGHTS}
    for weight in context.health_weights:
        weights[weight.dimension] = float(weight.weight)
    return weights


def compute_health(context: GrowthContext) -> dict:
    """Composite growth health snapshot."""
    open_ids = open_stage_ids(context)
    stages = {stage.id: stage for stage in context.stages if stage.lifecycle == "open"}
    max_open_position = max((stage.position for stage in stages.values()), default=0)
    positions = {stage.id: stage.position for stage in stages.values()}

    open_leads = [lead for lead in context.leads if lead.stage_id in open_ids]
    weighted_open = sum(
        float(lead.deal_value)
        * stage_weight(positions.get(stage_id, 0), max_open_position)
        for lead in open_leads
        if lead.deal_value is not None and (stage_id := lead.stage_id) is not None
    )

    revenue_values = [
        float(metric.value)
        for metric in context.metrics
        if metric.metric_type in ("revenue", "mrr", "arr")
    ]
    latest_revenue = revenue_values[-1] if revenue_values else 0.0
    avg_revenue = mean(revenue_values) if revenue_values else 0.0

    decided = [lead for lead in context.leads if lead.status in ("won", "lost")]
    won = sum(1 for lead in decided if lead.status == "won")
    win_rate = won / len(decided) if decided else 0.0

    sent = sum(
        1
        for attempt in context.attempts
        if attempt.status in ("sent", "delivered", "manually_sent")
    )
    replied = sum(1 for attempt in context.attempts if attempt.status == "replied")
    reply_rate = replied / sent if sent else 0.0

    attempts_and_events = len(context.attempts) + len(context.activity)
    dimensions = {
        "pipeline_health": _clamp(weighted_open / latest_revenue if latest_revenue else 0.0),
        "activity_level": _clamp(attempts_and_events / max(len(open_leads), 1)),
        "conversion_health": _clamp(win_rate * 2.0 + reply_rate * 0.5),
        "revenue_health": _clamp(latest_revenue / avg_revenue if avg_revenue else 0.0),
        "coverage_health": _clamp(weighted_open / latest_revenue if latest_revenue else 0.0),
    }

    labels = {
        "pipeline_health": "Weighted open pipeline value vs. last recorded revenue.",
        "activity_level": "Outreach attempts plus logged events per open lead.",
        "conversion_health": "Historical win rate and outreach reply rate blend.",
        "revenue_health": "Latest revenue vs. average period revenue.",
        "coverage_health": "Pipeline coverage ratio (weighted pipeline / revenue).",
    }

    weights = _effective_weights(context)
    score = sum(
        _clamp(dimensions[dimension]) * weights.get(dimension, 0.0) for dimension in dimensions
    )

    return {
        "score": round(score * 100, 1),
        "dimensions": {
            dimension: {"score": round(_clamp(value) * 100, 1), "label": labels[dimension]}
            for dimension, value in dimensions.items()
        },
        "weights": {dimension: round(weight, 4) for dimension, weight in weights.items()},
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
