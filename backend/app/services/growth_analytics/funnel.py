"""Funnel engine — deterministic funnel snapshot (M7).

Pure function over a :class:`GrowthContext`. Because the system only stores a
lead's *current* stage (no full stage-transition history), the funnel is a
snapshot-based approximation: each stage's ``entered`` count is the number of
leads currently at-or-before that stage, and ``stage_conversion`` is the
fraction of entered leads still present at the stage. Findings are labelled as
approximations so recommendations never overstate precision.
"""

from __future__ import annotations

from datetime import datetime

from app.services.growth_analytics.datatypes import GrowthContext


def compute_funnel(context: GrowthContext) -> dict:
    """Funnel snapshot: per-stage counts, cumulative entries, conversion, dropoff."""
    open_stages = [
        stage
        for stage in sorted(context.stages, key=lambda item: (item.position, item.name))
        if stage.lifecycle == "open"
    ]

    counts: dict = {stage.id: 0 for stage in open_stages}
    for lead in context.leads:
        if lead.stage_id in counts:
            counts[lead.stage_id] += 1

    entered = 0
    funnel: list[dict] = []
    for stage in open_stages:
        count = counts[stage.id]
        entered += count
        conversion = round(count / entered, 4) if entered else 0.0
        funnel.append(
            {
                "stage_id": str(stage.id),
                "name": stage.name,
                "position": stage.position,
                "count": count,
                "entered": entered,
                "stage_conversion": conversion,
                "dropoff": entered - count,
            }
        )

    won = sum(1 for lead in context.leads if lead.status == "won")
    lost = sum(1 for lead in context.leads if lead.status == "lost")

    return {
        "funnel": funnel,
        "entry": len(context.leads),
        "exit_won": won,
        "exit_lost": lost,
        "note": (
            "Snapshot approximation: counts reflect current stage placement; "
            "stage_transition history is not stored."
        ),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
