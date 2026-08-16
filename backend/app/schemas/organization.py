"""Organization API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrganizationBase(BaseModel):
    """Fields a client can set on an organization."""

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$")
    website: str | None = None
    timezone: str = "UTC"
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug", mode="before")
    @classmethod
    def slug_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class OrganizationCreate(OrganizationBase):
    """Payload to create an organization."""


class OrganizationUpdate(BaseModel):
    """Partial update of an organization (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(
        default=None, min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$"
    )
    website: str | None = None
    timezone: str | None = None
    settings: dict[str, Any] | None = None


class OrganizationRead(OrganizationBase):
    """Full organization representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class AISettings(BaseModel):
    """Per-organization AI defaults (stored under ``settings.ai``)."""

    provider: str | None = Field(default=None, min_length=1, max_length=50)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    # Per-org AI execution kill switch (F-SEC-3). True disables AI execution.
    kill_switch: bool = False


class OrganizationAISettingsRead(BaseModel):
    """Resolved AI settings: what's actually in effect for the org."""

    provider: str
    model: str
    overridden: bool
    kill_switch: bool


class OrganizationAISettingsUpdate(BaseModel):
    """Patch payload for per-org AI defaults."""

    provider: str | None = Field(default=None, min_length=1, max_length=50)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    kill_switch: bool | None = None
