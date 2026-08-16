"""Growth recommendation schemas — evidence-backed recommendations (M7)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import RecommendationPriority, RecommendationStatus
from app.schemas.common import Page


class GrowthRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    recommendation_type: str
    priority: RecommendationPriority
    confidence: RecommendationPriority
    status: RecommendationStatus
    title: str
    summary: str
    rationale: str | None = None
    action_type: str | None = None
    action_payload: dict[str, Any]
    source_analysis_id: uuid.UUID | None = None
    evidence: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class GrowthRecommendationListResponse(Page[GrowthRecommendationRead]):
    pass


class GrowthRecommendationUpdate(BaseModel):
    status: RecommendationStatus | None = None
    priority: RecommendationPriority | None = None
