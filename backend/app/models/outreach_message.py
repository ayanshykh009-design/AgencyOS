"""OutreachMessage model — reusable per-channel message templates."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachChannel

if TYPE_CHECKING:
    from app.models.outreach_attempt import OutreachAttempt


class OutreachMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A message template a campaign reuses across many leads."""

    __tablename__ = "outreach_messages"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_outreach_messages_org_name"),
        CheckConstraint("length(btrim(name)) > 0", name="chk_outreach_messages_name_not_blank"),
        CheckConstraint("length(btrim(body)) > 0", name="chk_outreach_messages_body_not_blank"),
        CheckConstraint("version >= 1", name="chk_outreach_messages_version"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[OutreachChannel] = mapped_column(
        Enum(OutreachChannel, name="outreach_channel", native_enum=True, validate_strings=True),
        nullable=False,
    )
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    outreach_attempts: Mapped[list[OutreachAttempt]] = relationship(back_populates="message")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<OutreachMessage id={self.id} name={self.name!r}>"
