"""Forecast engine — deterministic growth forecast (M7).

Pure function over a :class:`GrowthContext`. Produces a point forecast with
confidence bounds for the next period using one of four deterministic methods:

* ``linear_trend`` — OLS slope on the revenue series, projected forward.
* ``moving_average`` — mean of the last ``window`` revenue points.
* ``pipeline_weighted`` — weighted value of the open pipeline.
* ``seasonal_naive`` — prior same-period value (repeats last period).

The output mirrors the persisted ``growth_forecasts`` columns
(``point_estimate`` / ``lower_bound`` / ``upper_bound`` / ``series``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.kpis import open_stage_ids, stage_weight
from app.services.growth_analytics.stats import linear_fit

SUPPORTED_METHODS = ("linear_trend", "moving_average", "pipeline_weighted", "seasonal_naive")
DEFAULT_WINDOW = 3
DEFAULT_CONFIDENCE = 0.2


@dataclass
class ForecastResult:
    method: str
    point_estimate: float
    lower_bound: float
    upper_bound: float
    series: list[dict]
    errors: list[str]


def _revenue_series(context: GrowthContext) -> list[tuple[str, float]]:
    metrics = sorted(
        [metric for metric in context.metrics if metric.metric_type in ("revenue", "mrr", "arr")],
        key=lambda item: item.period_end,
    )
    seen: set[str] = set()
    series: list[tuple[str, float]] = []
    for metric in metrics:
        key = metric.period_end.strftime("%Y-%m")
        if key not in seen:
            seen.add(key)
            series.append((key, float(metric.value)))
    return series


def forecast_linear_trend(series: list[tuple[str, float]]) -> float:
    if len(series) < 2:
        return float(series[-1][1]) if series else 0.0
    values = [value for _, value in series]
    slope = linear_fit(list(range(len(values))), values)[0]
    return values[-1] + slope


def forecast_moving_average(series: list[tuple[str, float]], window: int) -> float:
    values = [value for _, value in series]
    if not values:
        return 0.0
    recent = values[-window:]
    return sum(recent) / len(recent)


def forecast_pipeline_weighted(context: GrowthContext) -> float:
    open_ids = open_stage_ids(context)
    max_open_position = max(
        (stage.position for stage in context.stages if stage.lifecycle == "open"),
        default=0,
    )
    positions = {stage.id: stage.position for stage in context.stages}
    total = 0.0
    for lead in context.leads:
        if lead.stage_id in open_ids and lead.deal_value is not None:
            total += float(lead.deal_value) * stage_weight(
                positions.get(lead.stage_id, 0), max_open_position
            )
    return round(total, 2)


def forecast_seasonal_naive(series: list[tuple[str, float]]) -> float:
    if not series:
        return 0.0
    return float(series[-1][1])


def compute_forecast(context: GrowthContext, method: str | None = None) -> ForecastResult:
    """Compute a deterministic forecast for the next period."""
    method = method or "linear_trend"
    errors: list[str] = []
    if method not in SUPPORTED_METHODS:
        errors.append(f"unsupported method '{method}'; using 'linear_trend'")
        method = "linear_trend"

    series = _revenue_series(context)
    if len(series) < 2 and method != "pipeline_weighted":
        errors.append("fewer than two revenue periods; forecast is a naive repetition")

    if method == "linear_trend":
        point = forecast_linear_trend(series)
    elif method == "moving_average":
        point = forecast_moving_average(series, DEFAULT_WINDOW)
    elif method == "pipeline_weighted":
        point = forecast_pipeline_weighted(context)
    else:
        point = forecast_seasonal_naive(series)

    point = max(0.0, point)
    band = max(point * DEFAULT_CONFIDENCE, 1.0)
    lower_bound = max(0.0, round(point - band, 2))
    upper_bound = round(point + band, 2)

    series_out = [{"period": period, "value": value} for period, value in series] + [
        {"period": "next", "value": round(point, 2)}
    ]

    return ForecastResult(
        method=method,
        point_estimate=round(point, 2),
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        series=series_out,
        errors=errors,
    )


def build_forecast_payload(context: GrowthContext, method: str | None = None) -> dict:
    """Forecast result as a JSON-safe dict for persistence."""
    result = compute_forecast(context, method)
    return {
        "method": result.method,
        "point_estimate": result.point_estimate,
        "lower_bound": result.lower_bound,
        "upper_bound": result.upper_bound,
        "series": result.series,
        "errors": result.errors,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
