"""ManualOutreachQueue model — human-triggered outreach tasks."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachChannel, OutreachStatus

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.user import User


class ManualOutreachQueue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A queued manual outreach task assigned to a user."""

    __tablename__ = "manual_outreach_queue"
    __table_args__ = (
        CheckConstraint("priority >= 0", name="chk_manual_outreach_priority"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
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
    priority: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column()
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column()

    lead: Mapped[Lead] = relationship(back_populates="manual_outreach_queue")
    assigned_user: Mapped[User | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ManualOutreachQueue id={self.id} status={self.status}>"
