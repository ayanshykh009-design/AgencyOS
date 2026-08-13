"""Knowledge item schemas (durable long-term knowledge)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class KnowledgeItemBase(BaseModel):
    source_memory_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    category: str = Field(default="general", min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class KnowledgeItemCreate(KnowledgeItemBase):
    organization_id: uuid.UUID


class KnowledgeItemUpdate(BaseModel):
    source_memory_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = Field(
        default=None, alias="metadata_", serialization_alias="metadata"
    )


class KnowledgeItemRead(KnowledgeItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class KnowledgeItemListResponse(Page[KnowledgeItemRead]):
    pass
