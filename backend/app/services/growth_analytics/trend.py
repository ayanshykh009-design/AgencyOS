"""Trend engine — deterministic trend detection (M7).

Pure function over a :class:`GrowthContext`. Detects monotonic/period-over-period
trends on lead and revenue metric series within the window.
"""

from __future__ import annotations

from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.stats import linear_fit, pct_change


def _trend_label(slope: float) -> str:
    if slope > 0.05:
        return "up"
    if slope < -0.05:
        return "down"
    return "flat"


def compute_trends(context: GrowthContext) -> dict:
    """Trend analysis snapshot."""
    leads_by_month: dict[str, list] = {}
    for lead in context.leads:
        if lead.created_at:
            key = lead.created_at.strftime("%Y-%m")
            leads_by_month.setdefault(key, []).append(lead)

    lead_series = sorted(
        [{"month": month, "count": len(leads)} for month, leads in leads_by_month.items()],
        key=lambda item: item["month"],
    )
    lead_counts = [float(item["count"]) for item in lead_series]
    lead_slope = (
        linear_fit(list(range(len(lead_counts))), lead_counts)[0] if len(lead_counts) >= 2 else 0.0
    )

    revenue_series = sorted(
        [
            {"month": metric.period_end.strftime("%Y-%m"), "value": float(metric.value)}
            for metric in context.metrics
            if metric.metric_type in ("revenue", "mrr", "arr")
        ],
        key=lambda item: item["month"],
    )
    revenue_values = [item["value"] for item in revenue_series]
    revenue_slope = (
        linear_fit(list(range(len(revenue_values))), revenue_values)[0]
        if len(revenue_values) >= 2
        else 0.0
    )

    last_revenue = revenue_values[-1] if revenue_values else 0.0
    prev_revenue = revenue_values[-2] if len(revenue_values) >= 2 else 0.0
    revenue_growth = pct_change(prev_revenue, last_revenue)

    return {
        "leads": {
            "series": lead_series,
            "count": len(lead_counts),
            "slope": round(lead_slope, 4),
            "trend": _trend_label(lead_slope),
        },
        "revenue": {
            "series": revenue_series,
            "count": len(revenue_values),
            "slope": round(revenue_slope, 4),
            "trend": _trend_label(revenue_slope),
            "growth_pct": round(revenue_growth, 4),
            "latest": last_revenue,
        },
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
