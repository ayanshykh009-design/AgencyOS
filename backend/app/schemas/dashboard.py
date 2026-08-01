"""Dashboard API schemas (aggregate snapshot for the UI)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.models.enums import LeadStatus
from app.schemas.activity import ActivityLogRead


class DashboardLeadCounts(BaseModel):
    """Lead counts by lifecycle status (plus total)."""

    model_config = ConfigDict(use_enum_values=True)

    new: int = 0
    researching: int = 0
    contacted: int = 0
    meeting_booked: int = 0
    proposal_sent: int = 0
    won: int = 0
    lost: int = 0
    total: int = 0

    @classmethod
    def from_status_counts(
        cls, counts: dict[LeadStatus, int], total: int
    ) -> DashboardLeadCounts:
        values: dict[str, int] = {status.value: 0 for status in LeadStatus}
        for status, count in counts.items():
            values[status.value] = count
        values["total"] = total
        return cls(**values)


class DashboardSummary(BaseModel):
    """Top-level dashboard snapshot."""

    leads: DashboardLeadCounts
    users: dict[str, int]
    conversations: dict[str, int]
    outreach: dict[str, int]
    imports: dict[str, int]
    activity: dict[str, list[ActivityLogRead]]
    usage: dict[str, float]
