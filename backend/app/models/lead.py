"""Lead model — a prospect with org-scoped duplicate protection.

Normalized dedup columns (``email_normalized``, ``phone_normalized``,
``website_domain``) are GENERATED in PostgreSQL; the ORM mirrors them with
``Computed`` so they are read-only on the application side. Unique partial
indexes in ``__table_args__`` mirror the database-level duplicate protection.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Computed, Enum, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import LeadStatus

if TYPE_CHECKING:
    from app.models.activity_log import ActivityLog
    from app.models.conversation import Conversation
    from app.models.follow_up import FollowUp
    from app.models.lead_research import LeadResearch
    from app.models.lead_source import LeadSource
    from app.models.manual_outreach_queue import ManualOutreachQueue
    from app.models.outreach_attempt import OutreachAttempt
    from app.models.user import User


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A prospect tracked by an organization."""

    __tablename__ = "leads"
    __table_args__ = (
        Index(
            "uq_leads_org_email",
            "organization_id",
            "email_normalized",
            unique=True,
            postgresql_where=text("email_normalized IS NOT NULL"),
        ),
        Index(
            "uq_leads_org_phone",
            "organization_id",
            "phone_normalized",
            unique=True,
            postgresql_where=text("phone_normalized IS NOT NULL"),
        ),
        Index(
            "uq_leads_org_website_domain",
            "organization_id",
            "website_domain",
            unique=True,
            postgresql_where=text("website_domain IS NOT NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead_sources.id", ondelete="SET NULL"), index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="lead_status", native_enum=True, validate_strings=True),
        default=LeadStatus.NEW,
        nullable=False,
    )
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    position: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    whatsapp: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    # Generated, read-only dedup keys (mirror PostgreSQL GENERATED columns).
    email_normalized: Mapped[str | None] = mapped_column(
        Computed("lower(btrim(email))"), nullable=True
    )
    phone_normalized: Mapped[str | None] = mapped_column(
        Computed("coalesce(normalize_phone(phone), normalize_phone(whatsapp))"), nullable=True
    )
    website_domain: Mapped[str | None] = mapped_column(
        Computed("normalize_domain(website)"), nullable=True
    )

    deleted_at: Mapped[datetime | None] = mapped_column()

    lead_source: Mapped[LeadSource | None] = relationship(back_populates="leads")
    owner: Mapped[User | None] = relationship()
    research: Mapped[LeadResearch | None] = relationship(back_populates="lead", uselist=False)
    outreach_attempts: Mapped[list[OutreachAttempt]] = relationship(back_populates="lead")
    follow_ups: Mapped[list[FollowUp]] = relationship(back_populates="lead")
    manual_outreach_queue: Mapped[list[ManualOutreachQueue]] = relationship(
        back_populates="lead"
    )
    conversations: Mapped[list[Conversation]] = relationship(back_populates="lead")
    activity_logs: Mapped[list[ActivityLog]] = relationship(back_populates="lead")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Lead id={self.id} email={self.email!r}>"
