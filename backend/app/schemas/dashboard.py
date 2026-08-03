"""Dashboard API schemas (aggregate snapshot for the UI)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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


class DashboardTasks(BaseModel):
    """Task workload snapshot (open / overdue / due today / completed)."""

    open: int = 0
    overdue: int = 0
    due_today: int = 0
    completed_30d: int = 0


class DashboardPipeline(BaseModel):
    """Deal-flow snapshot from the pipeline module."""

    won_deals: int = 0
    open_deals: int = 0
    won_revenue: float = 0.0
    unassigned_leads: int = 0


class DashboardSummary(BaseModel):
    """Top-level dashboard snapshot."""

    leads: DashboardLeadCounts
    users: dict[str, int]
    conversations: dict[str, int]
    outreach: dict[str, int]
    imports: dict[str, int]
    tasks: DashboardTasks = Field(default_factory=DashboardTasks)
    pipeline: DashboardPipeline = Field(default_factory=DashboardPipeline)
    activity: dict[str, list[ActivityLogRead]]
    usage: dict[str, float]
