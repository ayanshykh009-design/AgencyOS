"""Founder message model — a single turn in a founder conversation (org-scoped)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import FounderMessageSender

if TYPE_CHECKING:
    from app.models.founder_conversation import FounderConversation


class FounderMessage(UUIDPrimaryKeyMixin, Base):
    """One message in a founder conversation.

    Messages are append-only: the assistant's answer, the founder's prompt, and
    any tool results are all stored as messages. ``sent_at`` is the immutable
    timestamp; there is no mutable ``updated_at`` (a message is never edited).
    """

    __tablename__ = "founder_messages"
    __table_args__ = (
        CheckConstraint("length(btrim(body)) > 0", name="chk_founder_messages_body_not_blank"),
        Index("idx_founder_messages_conversation_sent", "conversation_id", "sent_at"),
        Index("idx_founder_messages_org_sent", "organization_id", "sent_at"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("founder_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_type: Mapped[FounderMessageSender] = mapped_column(
        Enum(
            FounderMessageSender,
            name="founder_message_sender",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[FounderConversation] = relationship(back_populates="messages")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<FounderMessage id={self.id} sender={self.sender_type}>"
