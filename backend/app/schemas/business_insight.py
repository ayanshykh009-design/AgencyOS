"""Business insight schemas (generated insight rows)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InsightSeverity, InsightStatus, InsightType
from app.schemas.common import Page


class BusinessInsightBase(BaseModel):
    insight_type: InsightType
    severity: InsightSeverity = InsightSeverity.INFO
    status: InsightStatus = InsightStatus.ACTIVE
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1)
    source_table: str | None = None
    source_row_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class BusinessInsightCreate(BusinessInsightBase):
    organization_id: uuid.UUID


class BusinessInsightUpdate(BaseModel):
    status: InsightStatus | None = None
    severity: InsightSeverity | None = None


class BusinessInsightRead(BusinessInsightBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BusinessInsightCounts(BaseModel):
    """Open insight count plus counts grouped by type."""

    open: int
    by_type: dict[InsightType, int]


class BusinessInsightListResponse(Page[BusinessInsightRead]):
    pass
