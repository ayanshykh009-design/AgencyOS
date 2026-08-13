"""OutreachAttempt model — one message send with delivery tracking."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachChannel, OutreachStatus

if TYPE_CHECKING:
    from app.models.follow_up import FollowUp
    from app.models.lead import Lead
    from app.models.outreach_message import OutreachMessage


class OutreachAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A concrete send of an outreach message to a lead."""

    __tablename__ = "outreach_attempts"
    __table_args__ = (
        CheckConstraint(
            "delivered_at IS NULL OR sent_at IS NOT NULL",
            name="chk_outreach_attempts_timing",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outreach_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outreach_messages.id", ondelete="SET NULL")
    )
    channel: Mapped[OutreachChannel] = mapped_column(
        Enum(OutreachChannel, name="outreach_channel", native_enum=True, validate_strings=True),
        nullable=False,
    )
    status: Mapped[OutreachStatus] = mapped_column(
        Enum(OutreachStatus, name="outreach_status", native_enum=True, validate_strings=True),
        default=OutreachStatus.QUEUED,
        nullable=False,
    )
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(index=True)
    sent_at: Mapped[datetime | None] = mapped_column()
    delivered_at: Mapped[datetime | None] = mapped_column()
    external_id: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )

    lead: Mapped[Lead] = relationship(back_populates="outreach_attempts")
    message: Mapped[OutreachMessage | None] = relationship(back_populates="outreach_attempts")
    follow_ups: Mapped[list[FollowUp]] = relationship(back_populates="outreach_attempt")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<OutreachAttempt id={self.id} status={self.status}>"
