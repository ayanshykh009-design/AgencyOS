"""Growth analytics engines — deterministic analysis for the growth agent (M7).

Each module is a pure function over :class:`GrowthContext` with no database
access; results are JSON-safe dicts that are persisted into ``growth_analyses``
(or used in-memory by tools/executor).
"""

from __future__ import annotations

from app.services.growth_analytics.activity import compute_activity
from app.services.growth_analytics.bottleneck import compute_bottlenecks
from app.services.growth_analytics.conversion import compute_conversion
from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.forecast import build_forecast_payload, compute_forecast
from app.services.growth_analytics.funnel import compute_funnel
from app.services.growth_analytics.health import compute_health
from app.services.growth_analytics.kpis import compute_kpis
from app.services.growth_analytics.opportunity import compute_opportunities
from app.services.growth_analytics.pipeline import compute_pipeline
from app.services.growth_analytics.recommendations import generate_recommendations
from app.services.growth_analytics.revenue import compute_revenue
from app.services.growth_analytics.scenario import apply_deltas
from app.services.growth_analytics.trend import compute_trends

__all__ = [
    "GrowthContext",
    "apply_deltas",
    "build_forecast_payload",
    "compute_activity",
    "compute_bottlenecks",
    "compute_conversion",
    "compute_forecast",
    "compute_funnel",
    "compute_health",
    "compute_kpis",
    "compute_opportunities",
    "compute_pipeline",
    "compute_revenue",
    "compute_trends",
    "generate_recommendations",
]
