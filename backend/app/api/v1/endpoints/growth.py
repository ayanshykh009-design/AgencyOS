"""Growth endpoints: periodized metrics, forecasts, and M7 growth intelligence."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.growth import (
    GrowthForecastCreate,
    GrowthForecastListResponse,
    GrowthForecastRead,
    GrowthForecastRunRequest,
    GrowthMetricCreate,
    GrowthMetricListResponse,
    GrowthMetricRead,
    GrowthMetricTypesResponse,
)
from app.schemas.growth_analysis import (
    GrowthAnalysisListResponse,
    GrowthAnalysisRead,
    GrowthAnalysisRunAllRequest,
    GrowthAnalysisRunRequest,
    GrowthHealthWeightCreate,
    GrowthHealthWeightRead,
    GrowthHealthWeightsResponse,
)
from app.schemas.growth_recommendation import (
    GrowthRecommendationListResponse,
    GrowthRecommendationRead,
    GrowthRecommendationUpdate,
)
from app.schemas.growth_scenario import (
    GrowthScenarioCreate,
    GrowthScenarioListResponse,
    GrowthScenarioRead,
)
from app.services.growth_analytics.health import DEFAULT_WEIGHTS
from app.services.growth_analytics_service import GrowthAnalyticsService
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
    metric = await service.create_metric(current_user.organization_id, metadata_=metadata, **data)
    return GrowthMetricRead.model_validate(metric)


@router.get(
    "/metrics/types",
    response_model=GrowthMetricTypesResponse,
    summary="Distinct metric types recorded",
    dependencies=[_read],
)
async def metric_types(db: DbSession, current_user: CurrentUser) -> GrowthMetricTypesResponse:
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
    forecast = await service.latest_forecast(current_user.organization_id, forecast_type)
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


# -- M7 analyses ------------------------------------------------------


@router.get(
    "/analyses",
    response_model=GrowthAnalysisListResponse,
    summary="List growth analysis snapshots",
    dependencies=[_read],
)
async def list_analyses(
    db: DbSession,
    current_user: CurrentUser,
    analysis_type: str | None = Query(default=None, max_length=50),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GrowthAnalysisListResponse:
    from app.models.enums import GrowthAnalysisStatus, GrowthAnalysisType

    service = GrowthAnalyticsService(db)
    items = await service.list_analyses(
        current_user.organization_id,
        analysis_type=GrowthAnalysisType(analysis_type) if analysis_type else None,
        status=GrowthAnalysisStatus(status_filter) if status_filter else None,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
    return GrowthAnalysisListResponse(
        items=[GrowthAnalysisRead.model_validate(a) for a in items], total=len(items)
    )


@router.post(
    "/analyses/run",
    response_model=GrowthAnalysisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Run one deterministic growth analysis",
    dependencies=[_manage],
)
async def run_analysis(
    body: GrowthAnalysisRunRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthAnalysisRead:
    service = GrowthAnalyticsService(db)
    analysis = await service.run_analysis(
        current_user.organization_id,
        analysis_type=body.analysis_type,
        period_start=body.period_start,
        period_end=body.period_end,
        generated_by=body.generated_by,
    )
    return GrowthAnalysisRead.model_validate(analysis)


@router.post(
    "/analyses/run-all",
    response_model=list[GrowthAnalysisRead],
    status_code=status.HTTP_201_CREATED,
    summary="Run every deterministic growth analysis (one snapshot per type)",
    dependencies=[_manage],
)
async def run_all_analyses(
    body: GrowthAnalysisRunAllRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> list[GrowthAnalysisRead]:
    service = GrowthAnalyticsService(db)
    analyses = await service.run_full_analysis(
        current_user.organization_id,
        period_start=body.period_start,
        period_end=body.period_end,
        generated_by=body.generated_by,
    )
    return [GrowthAnalysisRead.model_validate(a) for a in analyses]


@router.get(
    "/analyses/{analysis_id}",
    response_model=GrowthAnalysisRead,
    summary="Get a growth analysis snapshot",
    dependencies=[_read],
)
async def get_analysis(
    analysis_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthAnalysisRead:
    service = GrowthAnalyticsService(db)
    analysis = await service.get_analysis(current_user.organization_id, analysis_id)
    return GrowthAnalysisRead.model_validate(analysis)


# -- M7 recommendations ------------------------------------------------


@router.get(
    "/recommendations",
    response_model=GrowthRecommendationListResponse,
    summary="List growth recommendations",
    dependencies=[_read],
)
async def list_recommendations(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    priority: str | None = Query(default=None, max_length=10),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GrowthRecommendationListResponse:
    from app.models.enums import RecommendationPriority, RecommendationStatus

    service = GrowthAnalyticsService(db)
    items = await service.list_recommendations(
        current_user.organization_id,
        status=RecommendationStatus(status_filter) if status_filter else None,
        priority=RecommendationPriority(priority) if priority else None,
        limit=limit,
        offset=offset,
    )
    return GrowthRecommendationListResponse(
        items=[GrowthRecommendationRead.model_validate(r) for r in items], total=len(items)
    )


@router.get(
    "/recommendations/counts",
    response_model=dict,
    summary="Growth recommendation counts per triage status",
    dependencies=[_read],
)
async def recommendation_counts(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    service = GrowthAnalyticsService(db)
    return {
        k.value if hasattr(k, "value") else k: v
        for k, v in (await service.recommendation_counts(current_user.organization_id)).items()
    }


@router.patch(
    "/recommendations/{recommendation_id}",
    response_model=GrowthRecommendationRead,
    summary="Triage a growth recommendation (status/priority)",
    dependencies=[_manage],
)
async def update_recommendation(
    recommendation_id: uuid.UUID,
    body: GrowthRecommendationUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthRecommendationRead:
    service = GrowthAnalyticsService(db)
    recommendation = await service.update_recommendation(
        current_user.organization_id,
        recommendation_id,
        status=body.status,
        priority=body.priority,
    )
    return GrowthRecommendationRead.model_validate(recommendation)


# -- M7 scenarios -------------------------------------------------------


@router.get(
    "/scenarios",
    response_model=GrowthScenarioListResponse,
    summary="List saved growth scenarios",
    dependencies=[_read],
)
async def list_scenarios(
    db: DbSession,
    current_user: CurrentUser,
    forecast_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GrowthScenarioListResponse:
    service = GrowthAnalyticsService(db)
    items = await service.list_scenarios(
        current_user.organization_id,
        forecast_id=forecast_id,
        limit=limit,
        offset=offset,
    )
    return GrowthScenarioListResponse(
        items=[GrowthScenarioRead.model_validate(s) for s in items], total=len(items)
    )


@router.post(
    "/scenarios",
    response_model=GrowthScenarioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate and save a what-if scenario",
    dependencies=[_manage],
)
async def create_scenario(
    body: GrowthScenarioCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthScenarioRead:
    service = GrowthAnalyticsService(db)
    period_end = body.period_end or datetime.utcnow()
    period_start = body.period_start or period_end - timedelta(days=30)
    scenario = await service.create_scenario(
        current_user.organization_id,
        name=body.name,
        description=body.description,
        assumption_deltas=body.assumption_deltas,
        period_start=period_start,
        period_end=period_end,
        forecast_id=body.forecast_id,
        created_by_user_id=current_user.id,
    )
    return GrowthScenarioRead.model_validate(scenario)


@router.get(
    "/scenarios/{scenario_id}",
    response_model=GrowthScenarioRead,
    summary="Get a saved growth scenario",
    dependencies=[_read],
)
async def get_scenario(
    scenario_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthScenarioRead:
    service = GrowthAnalyticsService(db)
    scenario = await service.get_scenario(current_user.organization_id, scenario_id)
    return GrowthScenarioRead.model_validate(scenario)


@router.delete(
    "/scenarios/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved growth scenario",
    dependencies=[_manage],
)
async def delete_scenario(
    scenario_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    service = GrowthAnalyticsService(db)
    await service.delete_scenario(current_user.organization_id, scenario_id)


# -- M7 health weights ---------------------------------------------------


@router.get(
    "/health-weights",
    response_model=GrowthHealthWeightsResponse,
    summary="Active (or default) growth health weights",
    dependencies=[_read],
)
async def get_health_weights(
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthHealthWeightsResponse:
    service = GrowthAnalyticsService(db)
    active = await service.active_health_weights(current_user.organization_id)
    if active is None:
        return GrowthHealthWeightsResponse(version=0, weights={**DEFAULT_WEIGHTS}, is_default=True)
    return GrowthHealthWeightsResponse(
        version=active.version, weights=active.weights, is_default=False
    )


@router.post(
    "/health-weights",
    response_model=GrowthHealthWeightRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save a new active health-weight version",
    dependencies=[_manage],
)
async def upsert_health_weights(
    body: GrowthHealthWeightCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthHealthWeightRead:
    service = GrowthAnalyticsService(db)
    row = await service.upsert_health_weights(
        current_user.organization_id,
        weights=body.weights,
        created_by_user_id=current_user.id,
    )
    return GrowthHealthWeightRead.model_validate(row)


# -- M7 forecast generation ------------------------------------------------


@router.post(
    "/forecasts/run",
    response_model=GrowthForecastRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate and persist a deterministic forecast",
    dependencies=[_manage],
)
async def run_forecast(
    body: GrowthForecastRunRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> GrowthForecastRead:
    service = GrowthAnalyticsService(db)
    forecast = await service.run_forecast(
        current_user.organization_id,
        method=body.method,
        period_start=body.period_start,
        period_end=body.period_end,
        horizon_start=body.horizon_start,
        horizon_end=body.horizon_end,
        forecast_type=body.forecast_type,
    )
    return GrowthForecastRead.model_validate(forecast)
