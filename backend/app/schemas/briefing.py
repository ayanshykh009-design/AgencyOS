"""Briefing schemas (generated founder briefings)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BriefingType
from app.schemas.common import Page


class BriefingBase(BaseModel):
    briefing_type: BriefingType = BriefingType.DAILY
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class BriefingCreate(BriefingBase):
    organization_id: uuid.UUID


class BriefingRead(BriefingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class BriefingListResponse(Page[BriefingRead]):
    pass
