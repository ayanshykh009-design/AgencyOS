"""Growth service: periodized metrics + deterministic forecasts.

Thin orchestration over the M2 repositories. The *business forecast engine*
(generating forecasts) lands in M5 — this service only records and reads
periodized rows and forecast snapshots.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth_forecast import GrowthForecast
from app.models.growth_metric import GrowthMetric
from app.repositories.growth_forecast import GrowthForecastRepository
from app.repositories.growth_metric import GrowthMetricRepository
from app.services.base import commit_with_retry


class GrowthService:
    """Owns growth metrics/forecasts and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._metrics = GrowthMetricRepository(session)
        self._forecasts = GrowthForecastRepository(session)

    # -- metrics --------------------------------------------------------

    async def list_metrics(
        self,
        organization_id: uuid.UUID,
        *,
        metric_type: str,
        start: Any = None,
        end: Any = None,
        limit: int = 1000,
    ) -> list[GrowthMetric]:
        return await self._metrics.list_series(
            organization_id, metric_type, start=start, end=end, limit=limit
        )

    async def create_metric(
        self,
        organization_id: uuid.UUID,
        *,
        metric_type: str,
        period_start: Any,
        period_end: Any,
        value: Decimal,
        unit: str | None,
        metadata_: dict[str, Any],
    ) -> GrowthMetric:
        metric = GrowthMetric(
            organization_id=organization_id,
            metric_type=metric_type,
            period_start=period_start,
            period_end=period_end,
            value=value,
            unit=unit,
            metadata_=metadata_,
        )
        self._metrics.add(metric)
        await commit_with_retry(self._session)
        return metric

    async def metric_types(self, organization_id: uuid.UUID) -> list[str]:
        return await self._metrics.list_types(organization_id)

    async def get_metric(self, organization_id: uuid.UUID, metric_id: uuid.UUID) -> GrowthMetric:
        return await self._metrics.get_or_404(organization_id, metric_id)

    # -- forecasts ------------------------------------------------------

    async def list_forecasts(
        self,
        organization_id: uuid.UUID,
        *,
        forecast_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrowthForecast]:
        return await self._forecasts.list_by_type(
            organization_id, forecast_type=forecast_type, limit=limit, offset=offset
        )

    async def latest_forecast(
        self, organization_id: uuid.UUID, forecast_type: str
    ) -> GrowthForecast:
        from app.core.errors import AppError

        forecast = await self._forecasts.latest_by_type(organization_id, forecast_type)
        if forecast is None:
            raise AppError(
                code="growth_forecast.not_found",
                message="Forecast not found",
                status_code=404,
            )
        return forecast

    async def get_forecast(
        self, organization_id: uuid.UUID, forecast_id: uuid.UUID
    ) -> GrowthForecast:
        return await self._forecasts.get_or_404(organization_id, forecast_id)

    async def create_forecast(
        self,
        organization_id: uuid.UUID,
        *,
        forecast_type: str,
        horizon_start: Any,
        horizon_end: Any,
        total_value: Decimal,
        confidence_low: Decimal | None,
        confidence_high: Decimal | None,
        model_config: dict[str, Any],
    ) -> GrowthForecast:
        forecast = GrowthForecast(
            organization_id=organization_id,
            forecast_type=forecast_type,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            total_value=total_value,
            confidence_low=confidence_low,
            confidence_high=confidence_high,
            model_config=model_config,
        )
        self._forecasts.add(forecast)
        await commit_with_retry(self._session)
        return forecast
