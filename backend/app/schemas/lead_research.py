"""LeadResearch API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_RESEARCH_STATUSES = ("pending", "in_progress", "completed", "failed")


class LeadResearchBase(BaseModel):
    """Fields a client can set on research."""

    status: str = "pending"
    company_overview: str | None = None
    pain_points: list[Any] = Field(default_factory=list)
    tech_stack: list[Any] = Field(default_factory=list)
    recent_news: list[Any] = Field(default_factory=list)
    linkedin_summary: str | None = None
    icp_match_score: int | None = Field(default=None, ge=0, le=100)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    research_source: str | None = None

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, v: str) -> str:
        if v not in _RESEARCH_STATUSES:
            raise ValueError(f"invalid research status: {v!r}")
        return v


class LeadResearchCreate(LeadResearchBase):
    """Payload to create research for a lead."""

    lead_id: UUID
    organization_id: UUID


class LeadResearchUpdate(BaseModel):
    """Partial update of research (all fields optional)."""

    status: str | None = None
    company_overview: str | None = None
    pain_points: list[Any] | None = None
    tech_stack: list[Any] | None = None
    recent_news: list[Any] | None = None
    linkedin_summary: str | None = None
    icp_match_score: int | None = Field(default=None, ge=0, le=100)
    raw_data: dict[str, Any] | None = None
    research_source: str | None = None
    researched_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def status_must_be_known(cls, v: str | None) -> str | None:
        if v is not None and v not in _RESEARCH_STATUSES:
            raise ValueError(f"invalid research status: {v!r}")
        return v


class LeadResearchRead(LeadResearchBase):
    """Full research representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: UUID
    organization_id: UUID
    researched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
