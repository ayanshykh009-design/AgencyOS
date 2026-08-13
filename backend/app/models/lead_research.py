"""LeadResearch model — enrichment output, one row per lead."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.lead import Lead


class LeadResearch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """AI/manual research about a lead (one row per lead)."""

    __tablename__ = "lead_research"
    __table_args__ = (
        UniqueConstraint("lead_id", name="uq_lead_research_lead"),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'failed')",
            name="chk_lead_research_status",
        ),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    company_overview: Mapped[str | None] = mapped_column(Text)
    pain_points: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    tech_stack: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    recent_news: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    linkedin_summary: Mapped[str | None] = mapped_column(Text)
    icp_match_score: Mapped[int | None] = mapped_column(Integer)
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    research_source: Mapped[str | None] = mapped_column(Text)
    researched_at: Mapped[datetime | None] = mapped_column()

    lead: Mapped[Lead] = relationship(back_populates="research")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LeadResearch id={self.id} lead_id={self.lead_id}>"
