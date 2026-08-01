"""ProviderUsage API schemas (usage accounting, no credentials)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProviderUsageBase(BaseModel):
    """Fields a client can set on a usage record."""

    model_config = ConfigDict(populate_by_name=True)

    provider: str = Field(min_length=1, max_length=64)
    feature: str = Field(min_length=1, max_length=64)
    usage_date: date
    request_count: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(
        default_factory=dict, alias="metadata_", serialization_alias="metadata"
    )


class ProviderUsageCreate(ProviderUsageBase):
    """Payload to record or upsert a usage rollup."""

    organization_id: UUID


class ProviderUsageUpdate(BaseModel):
    """Partial update of a usage rollup (all fields optional)."""

    model_config = ConfigDict(populate_by_name=True)

    request_count: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = Field(
        default=None, alias="metadata_", serialization_alias="metadata"
    )


class ProviderUsageRead(ProviderUsageBase):
    """Full usage rollup returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime
