"""Pipeline engine — deterministic pipeline analysis (M7).

Pure function over a :class:`GrowthContext`. Summarizes the open pipeline by
stage with close-probability-weighted value and an overall expected value.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.kpis import open_stage_ids, stage_weight
from app.services.growth_analytics.stats import sum_decimal


def compute_pipeline(context: GrowthContext) -> dict:
    """Pipeline snapshot: per-stage counts/values, weighted value, expected value."""
    open_ids = open_stage_ids(context)
    max_open_position = max(
        (stage.position for stage in context.stages if stage.lifecycle == "open"),
        default=0,
    )
    positions = {stage.id: stage.position for stage in context.stages}
    open_stages = [
        stage
        for stage in sorted(context.stages, key=lambda item: (item.position, item.name))
        if stage.lifecycle == "open"
    ]

    rows: dict = {
        stage.id: {"count": 0, "value": Decimal("0"), "weighted": 0.0} for stage in open_stages
    }
    open_leads = [lead for lead in context.leads if lead.stage_id in open_ids]
    for lead in open_leads:
        row = rows.get(lead.stage_id)
        if row is None:
            continue
        row["count"] += 1
        if lead.deal_value is not None:
            row["value"] += lead.deal_value
            probability = stage_weight(positions.get(lead.stage_id, 0), max_open_position)
            row["weighted"] += float(lead.deal_value) * probability

    by_stage = [
        {
            "stage_id": str(stage.id),
            "name": stage.name,
            "position": stage.position,
            "count": rows[stage.id]["count"],
            "value": float(rows[stage.id]["value"]),
            "weighted_value": round(rows[stage.id]["weighted"], 2),
        }
        for stage in open_stages
    ]

    open_value = sum_decimal(lead.deal_value for lead in open_leads)
    weighted_value = sum(row["weighted"] for row in rows.values())

    return {
        "total_open": len(open_leads),
        "open_value": float(open_value),
        "weighted_value": round(weighted_value, 2),
        "expected_value": round(weighted_value, 2),
        "by_stage": by_stage,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
