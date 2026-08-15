"""Intelligence signal schemas — Founder Intelligence & Growth Triage (M9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    IntelligenceConfidence,
    IntelligenceSignalSeverity,
    IntelligenceSignalStatus,
    SignalCategory,
    SignalSourceType,
)
from app.schemas.common import Page


class IntelligenceSignalRead(BaseModel):
    """Public shape of one triaged signal (the M9->frontend contract).

    ``priority_components`` carries the versioned component scores that
    produced ``priority_score``; ``business_impact`` is ``None``-safe (amount
    is omitted when the source carries no monetary figure, never invented).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    signal_category: SignalCategory
    source_type: SignalSourceType
    source_row_id: uuid.UUID | None = None
    title: str
    summary: str
    severity: IntelligenceSignalSeverity
    business_impact: dict[str, Any]
    priority_score: float
    priority_components: dict[str, Any]
    evidence: list[dict[str, Any]]
    recommended_next_step: str | None = None
    confidence: IntelligenceConfidence
    status: IntelligenceSignalStatus
    first_seen_at: datetime
    last_triaged_at: datetime | None = None
    acknowledged_by_user_id: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
    last_notified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IntelligenceSignalListResponse(Page[IntelligenceSignalRead]):
    pass


class IntelligenceSignalUpdate(BaseModel):
    """Acknowledge or dismiss a signal.

    The triage worker is the only writer of everything else; the API must
    never mutate M7/M8 source rows through a signal patch.
    """

    status: IntelligenceSignalStatus


class IntelligenceSignalSummary(BaseModel):
    """Roll-up counts for the founder intelligence surface."""

    active: int
    acknowledged: int
    dismissed: int
    superseded: int
    high_priority: int
    medium_priority: int
    low_priority: int
    highest_priority_score: float | None = None
