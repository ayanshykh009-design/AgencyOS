"""Growth schemas (periodized metrics + deterministic forecasts)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class GrowthMetricBase(BaseModel):
    metric_type: str = Field(min_length=1, max_length=100)
    period_start: datetime
    period_end: datetime
    value: Decimal = Field(ge=0)
    unit: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class GrowthMetricCreate(GrowthMetricBase):
    organization_id: uuid.UUID


class GrowthMetricRead(GrowthMetricBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime


class GrowthMetricListResponse(Page[GrowthMetricRead]):
    pass


class GrowthForecastCreate(BaseModel):
    forecast_type: str = Field(min_length=1, max_length=100)
    horizon_start: datetime
    horizon_end: datetime
    total_value: Decimal = Field(ge=0)
    confidence_low: Decimal | None = None
    confidence_high: Decimal | None = None
    method: str | None = Field(default=None, min_length=1, max_length=100)
    base_period_start: datetime | None = None
    base_period_end: datetime | None = None
    point_estimate: Decimal | None = Field(default=None, ge=0)
    lower_bound: Decimal | None = Field(default=None, ge=0)
    upper_bound: Decimal | None = Field(default=None, ge=0)
    series: list[dict[str, Any]] = Field(default_factory=list)
    errors: dict[str, Any] = Field(default_factory=dict)
    model_config_: dict[str, Any] = Field(
        default_factory=dict, alias="model_config", serialization_alias="model_config"
    )


class GrowthForecastRead(GrowthForecastCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class GrowthMetricTypesResponse(BaseModel):
    """Distinct growth metric types recorded for an organization."""

    types: list[str]


class GrowthForecastListResponse(Page[GrowthForecastRead]):
    pass


class GrowthForecastRunRequest(BaseModel):
    """Generate a deterministic forecast via the M7 forecast engine."""

    method: str = Field(
        default="linear_trend",
        min_length=1,
        max_length=100,
        pattern="^(linear_trend|moving_average|pipeline_weighted|seasonal_naive)$",
    )
    period_start: datetime
    period_end: datetime
    horizon_start: datetime
    horizon_end: datetime
    forecast_type: str = Field(default="revenue", min_length=1, max_length=100)
