"""Conversation model — a reply thread with a lead."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachChannel

if TYPE_CHECKING:
    from app.models.conversation_message import ConversationMessage
    from app.models.lead import Lead


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A thread of back-and-forth messages with a lead on one channel."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "channel",
            "external_thread_id",
            name="uq_conversations_external_thread",
        ),
        Index(
            "uq_conversations_open_per_channel",
            "lead_id",
            "channel",
            unique=True,
            postgresql_where=text("is_open"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[OutreachChannel] = mapped_column(
        Enum(OutreachChannel, name="outreach_channel", native_enum=True, validate_strings=True),
        nullable=False,
    )
    external_thread_id: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column()

    lead: Mapped[Lead] = relationship(back_populates="conversations")
    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Conversation id={self.id} channel={self.channel}>"
