"""Growth scenario schemas — saved what-if projections (M7)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class GrowthScenarioCreate(BaseModel):
    forecast_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    assumption_deltas: dict[str, Any] = Field(default_factory=dict)
    period_start: datetime | None = Field(
        default=None, description="Analysis window start (defaults to 30 days ago)."
    )
    period_end: datetime | None = Field(
        default=None, description="Analysis window end (defaults to now)."
    )


class GrowthScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    forecast_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    assumption_deltas: dict[str, Any]
    result: dict[str, Any]
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class GrowthScenarioListResponse(Page[GrowthScenarioRead]):
    pass
