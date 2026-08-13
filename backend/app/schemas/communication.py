"""Founder communications summary schema.

Read-only aggregation over the Phase 5D inbox surfaces (notifications,
approvals, briefings, insights) presented to the current user. No AI or
delivery logic lives here — this is the API contract for the founder
communication layer's summary view.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.briefing import BriefingRead


class CommunicationsSummary(BaseModel):
    """Single-view digest of the founder communication surfaces."""

    unread_notifications: int
    pending_approvals: int
    active_insights: int
    latest_briefing: BriefingRead | None = None
