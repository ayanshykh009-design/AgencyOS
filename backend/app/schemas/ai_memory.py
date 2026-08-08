"""AI memory schemas (working + long-term memory store)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MemoryScope, MemoryType
from app.schemas.common import Page


class AiMemoryBase(BaseModel):
    memory_type: MemoryType = MemoryType.WORKING
    scope: MemoryScope
    source_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str = Field(min_length=1)
    importance: int = Field(default=1, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class AiMemoryCreate(AiMemoryBase):
    organization_id: uuid.UUID


class AiMemoryUpdate(BaseModel):
    """Partial update of a memory row (type is immutable once created)."""

    scope: MemoryScope | None = None
    source_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, min_length=1)
    importance: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = Field(
        default=None, alias="metadata_", serialization_alias="metadata"
    )


class AiMemoryRead(AiMemoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AiMemoryListResponse(Page[AiMemoryRead]):
    pass
