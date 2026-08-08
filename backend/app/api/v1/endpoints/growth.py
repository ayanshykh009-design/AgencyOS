"""Growth endpoints: periodized metrics + deterministic forecasts."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.growth import (
    GrowthForecastCreate,
    GrowthForecastListResponse,
    GrowthForecastRead,
    GrowthMetricCreate,
    GrowthMetricListResponse,
    GrowthMetricRead,
    GrowthMetricTypesResponse,
)
from app.services.growth_service import GrowthService

router = APIRouter()

_read = Depends(require_permission(Permission.GROWTH_READ))
_manage = Depends(require_permission(Permission.GROWTH_MANAGE))

_metadata_key = "model_config_"


# -- metrics ---------------------------------------------------------


@router.get(
    "/metrics",
    response_model=GrowthMetricListResponse,
    summary="Time series for a metric type (optional window)",
    dependencies=[_read],
)
async def list_metrics(
    db: DbSession,
    current_user: CurrentUser,
    metric_type: str = Query(min_length=1, max_length=100),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
) -> GrowthMetricListResponse:
    service = GrowthService(db)
    items = await service.list_metrics(
        current_user.organization_id,
        metric_type=metric_type,
        start=start,
        end=end,
        limit=limit,
    )
    return GrowthMetricListResponse(
        items=[GrowthMetricRead.model_validate(m) for m in items], total=len(items)
    )


@router.post(
    "/metrics",
    response_model=GrowthMetricRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a growth metric",
    dependencies=[_manage],
)
async def create_metric(
    body: GrowthMetricCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthMetricRead:
    service = GrowthService(db)
    data = body.model_dump(exclude={"organization_id"})
    metadata = data.pop("metadata", None) or {}
    metric = await service.create_metric(
        current_user.organization_id, metadata_=metadata, **data
    )
    return GrowthMetricRead.model_validate(metric)


@router.get(
    "/metrics/types",
    response_model=GrowthMetricTypesResponse,
    summary="Distinct metric types recorded",
    dependencies=[_read],
)
async def metric_types(
    db: DbSession, current_user: CurrentUser
) -> GrowthMetricTypesResponse:
    service = GrowthService(db)
    types = await service.metric_types(current_user.organization_id)
    return GrowthMetricTypesResponse(types=types)


# -- forecasts -------------------------------------------------------


@router.get(
    "/forecasts",
    response_model=GrowthForecastListResponse,
    summary="List growth forecasts (optional type filter)",
    dependencies=[_read],
)
async def list_forecasts(
    db: DbSession,
    current_user: CurrentUser,
    forecast_type: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GrowthForecastListResponse:
    service = GrowthService(db)
    items = await service.list_forecasts(
        current_user.organization_id,
        forecast_type=forecast_type,
        limit=limit,
        offset=offset,
    )
    return GrowthForecastListResponse(
        items=[GrowthForecastRead.model_validate(f) for f in items], total=len(items)
    )


@router.get(
    "/forecasts/latest",
    response_model=GrowthForecastRead,
    summary="Most recent forecast for a type",
    dependencies=[_read],
)
async def latest_forecast(
    db: DbSession,
    current_user: CurrentUser,
    forecast_type: str = Query(min_length=1, max_length=100),
) -> GrowthForecastRead:
    service = GrowthService(db)
    forecast = await service.latest_forecast(
        current_user.organization_id, forecast_type
    )
    return GrowthForecastRead.model_validate(forecast)


@router.post(
    "/forecasts",
    response_model=GrowthForecastRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a growth forecast",
    dependencies=[_manage],
)
async def create_forecast(
    body: GrowthForecastCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthForecastRead:
    service = GrowthService(db)
    data = body.model_dump()
    model_config = data.pop(_metadata_key, None) or {}
    forecast = await service.create_forecast(
        current_user.organization_id, model_config=model_config, **data
    )
    return GrowthForecastRead.model_validate(forecast)


@router.get(
    "/forecasts/{forecast_id}",
    response_model=GrowthForecastRead,
    summary="Get a growth forecast",
    dependencies=[_read],
)
async def get_forecast(
    forecast_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthForecastRead:
    service = GrowthService(db)
    forecast = await service.get_forecast(current_user.organization_id, forecast_id)
    return GrowthForecastRead.model_validate(forecast)


@router.get(
    "/metrics/{metric_id}",
    response_model=GrowthMetricRead,
    summary="Get a growth metric",
    dependencies=[_read],
)
async def get_metric(
    metric_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthMetricRead:
    service = GrowthService(db)
    metric = await service.get_metric(current_user.organization_id, metric_id)
    return GrowthMetricRead.model_validate(metric)
