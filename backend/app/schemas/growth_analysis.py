"""Growth analysis schemas — deterministic analysis snapshots + health weights."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GrowthAnalysisStatus, GrowthAnalysisType
from app.schemas.common import Page


class GrowthAnalysisRunRequest(BaseModel):
    """Trigger a deterministic analysis engine over a window."""

    analysis_type: GrowthAnalysisType
    period_start: datetime
    period_end: datetime
    generated_by: str = Field(default="user", min_length=1, max_length=100)


class GrowthAnalysisRunAllRequest(BaseModel):
    """Run every deterministic engine over a window (one snapshot per type)."""

    period_start: datetime
    period_end: datetime
    generated_by: str = Field(default="user", min_length=1, max_length=100)


class GrowthAnalysisBase(BaseModel):
    analysis_type: GrowthAnalysisType
    period_start: datetime
    period_end: datetime
    health_score: Decimal | None = Field(default=None, ge=0, le=100)
    summary: str = Field(min_length=1, max_length=4000)
    details: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    weights: dict[str, Any] = Field(default_factory=dict)
    metrics_used: list[str] = Field(default_factory=list)


class GrowthAnalysisRead(GrowthAnalysisBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    status: GrowthAnalysisStatus
    error: str | None = None
    generated_by: str
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class GrowthAnalysisListResponse(Page[GrowthAnalysisRead]):
    pass


class GrowthAnalysisRunResponse(GrowthAnalysisRead):
    """A persisted analysis snapshot (also used for full-run results)."""


class GrowthHealthWeightCreate(BaseModel):
    weights: dict[str, Decimal | float | int] = Field(default_factory=dict)


class GrowthHealthWeightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    version: int
    weights: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GrowthHealthWeightsResponse(BaseModel):
    """Active (or default) weight set + the resolved version."""

    version: int
    weights: dict[str, Any]
    is_default: bool
