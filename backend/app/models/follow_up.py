"""FollowUp model — a scheduled follow-up in an outreach sequence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachChannel, OutreachStatus

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.outreach_attempt import OutreachAttempt


class FollowUp(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A follow-up message for a lead, ordered within a sequence."""

    __tablename__ = "follow_ups"
    __table_args__ = (
        UniqueConstraint(
            "lead_id",
            "outreach_attempt_id",
            "sequence_position",
            name="uq_follow_ups_position",
        ),
        CheckConstraint("sequence_position >= 1", name="chk_follow_ups_position"),
        CheckConstraint("delay_days >= 0", name="chk_follow_ups_delay_days"),
        CheckConstraint("length(btrim(body)) > 0", name="chk_follow_ups_body_not_blank"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outreach_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outreach_attempts.id", ondelete="CASCADE")
    )
    channel: Mapped[OutreachChannel] = mapped_column(
        Enum(
            OutreachChannel,
            name="outreach_channel",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    sequence_position: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    delay_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column()
    status: Mapped[OutreachStatus] = mapped_column(
        Enum(
            OutreachStatus,
            name="outreach_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=OutreachStatus.QUEUED,
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column()

    lead: Mapped[Lead] = relationship(back_populates="follow_ups")
    outreach_attempt: Mapped[OutreachAttempt | None] = relationship(back_populates="follow_ups")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<FollowUp id={self.id} position={self.sequence_position}>"
