"""Bottleneck engine — deterministic bottleneck detection (M7).

Pure function over a :class:`GrowthContext`. Identifies funnel stages with the
largest relative dropoff and thin open-pipeline stages; reports them with a
severity heuristic so downstream engines can emit targeted recommendations.
"""

from __future__ import annotations

from app.services.growth_analytics.datatypes import GrowthContext


def compute_bottlenecks(context: GrowthContext) -> dict:
    """Bottleneck analysis snapshot."""
    open_stages = [
        stage
        for stage in sorted(context.stages, key=lambda item: (item.position, item.name))
        if stage.lifecycle == "open"
    ]
    counts = {stage.id: 0 for stage in open_stages}
    for lead in context.leads:
        if lead.stage_id in counts:
            counts[lead.stage_id] += 1

    bottlenecks: list[dict] = []
    entered = 0
    for index, stage in enumerate(open_stages):
        count = counts[stage.id]
        entered += count
        if index == 0 or not entered:
            continue
        prev_count = entered - count
        dropoff = prev_count - count
        dropoff_ratio = dropoff / prev_count if prev_count else 0.0
        if dropoff > 0:
            severity = (
                "high" if dropoff_ratio >= 0.5 else "medium" if dropoff_ratio >= 0.25 else "low"
            )
            bottlenecks.append(
                {
                    "stage": stage.name,
                    "stage_id": str(stage.id),
                    "position": stage.position,
                    "entered": prev_count,
                    "current": count,
                    "dropoff": dropoff,
                    "dropoff_ratio": round(dropoff_ratio, 4),
                    "severity": severity,
                }
            )

    bottlenecks.sort(key=lambda item: item["dropoff_ratio"], reverse=True)
    primary = bottlenecks[0] if bottlenecks else None

    return {
        "bottlenecks": bottlenecks,
        "primary": primary,
        "note": ("Relative dropoff between consecutive open stages; snapshot-based."),
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
