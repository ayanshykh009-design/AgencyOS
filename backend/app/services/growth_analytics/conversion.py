"""Conversion engine — deterministic conversion analysis (M7).

Pure function over a :class:`GrowthContext`. Computes win/loss rates, the
overall lead-to-won conversion, and stage-to-stage conversion between
consecutive open stages (relative-size approximation).
"""

from __future__ import annotations

from datetime import datetime

from app.services.growth_analytics.datatypes import GrowthContext


def compute_conversion(context: GrowthContext) -> dict:
    """Conversion snapshot: win/loss rates, overall conversion, stage-to-stage."""
    won = sum(1 for lead in context.leads if lead.status == "won")
    lost = sum(1 for lead in context.leads if lead.status == "lost")
    total = len(context.leads)
    decided = won + lost

    open_stages = [
        stage
        for stage in sorted(context.stages, key=lambda item: (item.position, item.name))
        if stage.lifecycle == "open"
    ]
    counts = {stage.id: 0 for stage in open_stages}
    for lead in context.leads:
        if lead.stage_id in counts:
            counts[lead.stage_id] += 1

    stage_to_stage: list[dict] = []
    for index, stage in enumerate(open_stages[:-1]):
        nxt = open_stages[index + 1]
        count_from = counts[stage.id]
        count_to = counts[nxt.id]
        stage_to_stage.append(
            {
                "from_stage": stage.name,
                "from_stage_id": str(stage.id),
                "to_stage": nxt.name,
                "to_stage_id": str(nxt.id),
                "count_from": count_from,
                "count_to": count_to,
                "conversion": round(count_to / count_from, 4) if count_from else 0.0,
            }
        )

    proposal_counts = [
        counts[stage.id] for stage in open_stages if "proposal" in stage.name.lower()
    ]
    meeting_counts = [counts[stage.id] for stage in open_stages if "meeting" in stage.name.lower()]
    proposals = sum(proposal_counts)
    meetings = sum(meeting_counts)

    return {
        "win_rate": round(won / decided, 4) if decided else 0.0,
        "loss_rate": round(lost / decided, 4) if decided else 0.0,
        "overall_conversion": round(won / total, 4) if total else 0.0,
        "stage_to_stage": stage_to_stage,
        "proposal_win_conversion": round(won / (proposals + won), 4) if (proposals + won) else 0.0,
        "meeting_to_won": round(won / (meetings + won), 4) if (meetings + won) else 0.0,
        "proposal_count": proposals,
        "meeting_count": meetings,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
