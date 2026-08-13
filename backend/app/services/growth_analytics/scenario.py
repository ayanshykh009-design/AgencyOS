"""Scenario engine — deterministic what-if scenario evaluation (M7).

Pure function over a :class:`GrowthContext`. Applies relative deltas
(``new_leads_delta``, ``conversion_delta``, ``win_rate_delta``,
``avg_deal_value_delta``) and simulates the funnel math to produce projected
closed deals and revenue for the period. Deltas are multipliers: 1.0 = no
change, 1.2 = +20%.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.stats import mean

_DEFAULT_DELTAS = {
    "new_leads_delta": 1.0,
    "conversion_delta": 1.0,
    "win_rate_delta": 1.0,
    "avg_deal_value_delta": 1.0,
}


def _decimal(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("1")


def apply_deltas(context: GrowthContext, params: dict) -> dict:
    """Apply relative deltas and return the simulated outcome for the period."""
    deltas = {**_DEFAULT_DELTAS, **params}

    leads_count = len(context.leads)
    conversion_rate = _funnel_conversion(context)
    win_rate = _historical_win_rate(context)
    avg_deal_value = _historical_avg_deal_value(context)

    projected_leads = leads_count * _decimal(deltas["new_leads_delta"])
    projected_leads = max(0.0, float(projected_leads))

    projected_conversion = conversion_rate * float(deltas["conversion_delta"])
    projected_win_rate = win_rate * float(deltas["win_rate_delta"])
    projected_avg_deal = avg_deal_value * float(deltas["avg_deal_value_delta"])

    closed_deals = projected_leads * projected_conversion * projected_win_rate
    revenue = closed_deals * projected_avg_deal

    return {
        "params": {**_DEFAULT_DELTAS, **params},
        "baseline": {
            "leads": leads_count,
            "conversion_rate": round(conversion_rate, 4),
            "win_rate": round(win_rate, 4),
            "avg_deal_value": round(avg_deal_value, 2),
        },
        "projected": {
            "leads": round(projected_leads, 2),
            "conversion_rate": round(projected_conversion, 4),
            "win_rate": round(projected_win_rate, 4),
            "avg_deal_value": round(projected_avg_deal, 2),
            "closed_deals": round(closed_deals, 2),
            "revenue": round(revenue, 2),
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _funnel_conversion(context: GrowthContext) -> float:
    decided = [lead for lead in context.leads if lead.status in ("won", "lost")]
    won = sum(1 for lead in decided if lead.status == "won")
    return won / len(decided) if decided else 0.0


def _historical_win_rate(context: GrowthContext) -> float:
    decided = [lead for lead in context.leads if lead.status in ("won", "lost")]
    won = sum(1 for lead in decided if lead.status == "won")
    return won / len(decided) if decided else 0.0


def _historical_avg_deal_value(context: GrowthContext) -> float:
    values = [lead.deal_value for lead in context.leads if lead.deal_value is not None]
    return float(mean(values)) if values else 0.0
