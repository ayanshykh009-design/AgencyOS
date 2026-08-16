"""Opportunity engine — deterministic opportunity detection (M7).

Pure function over a :class:`GrowthContext`. Surfaces the highest-expected-value
open deals and the highest-value won deals, which feed the growth agent's
opportunity insights and recommendations.
"""

from __future__ import annotations

from datetime import datetime

from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.kpis import open_stage_ids, stage_weight


def compute_opportunities(context: GrowthContext) -> dict:
    """Opportunity snapshot: top weighted open deals and top wins."""
    open_ids = open_stage_ids(context)
    max_open_position = max(
        (stage.position for stage in context.stages if stage.lifecycle == "open"),
        default=0,
    )
    positions = {stage.id: stage.position for stage in context.stages}

    open_leads = [
        lead for lead in context.leads if lead.stage_id in open_ids and lead.deal_value is not None
    ]

    def expected_value(lead) -> float:
        position = positions.get(lead.stage_id, 0)
        probability = stage_weight(position, max_open_position)
        return float(lead.deal_value) * probability

    def probability_of(lead) -> float:
        return round(stage_weight(positions.get(lead.stage_id, 0), max_open_position), 4)

    top_opportunities = sorted(open_leads, key=lambda lead: expected_value(lead), reverse=True)[:5]

    top_won = sorted(
        [
            lead
            for lead in context.leads
            if lead.status == "won" and lead.deal_value is not None and lead.won_at
        ],
        key=lambda lead: (lead.won_at or datetime.min, float(lead.deal_value or 0)),
        reverse=True,
    )[:5]

    return {
        "top_opportunities": [
            {
                "lead_id": str(lead.id),
                "name": lead.name,
                "stage": lead.stage_id,
                "stage_name": next(
                    (stage.name for stage in context.stages if stage.id == lead.stage_id),
                    None,
                ),
                "deal_value": float(lead.deal_value) if lead.deal_value is not None else 0.0,
                "expected_value": round(expected_value(lead), 2),
                "probability": probability_of(lead),
            }
            for lead in top_opportunities
        ],
        "recent_won": [
            {
                "lead_id": str(lead.id),
                "name": lead.name,
                "deal_value": float(lead.deal_value) if lead.deal_value is not None else 0.0,
                "won_at": (lead.won_at or datetime.min).isoformat() + "Z",
            }
            for lead in top_won
        ],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
