"""ConversationMessage model — append-only thread history."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ConversationSender

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.user import User


class ConversationMessage(UUIDPrimaryKeyMixin, Base):
    """One message within a conversation (append-only, no ``updated_at``)."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(body)) > 0", name="chk_conversation_messages_body_not_blank"
        ),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    sender_type: Mapped[ConversationSender] = mapped_column(
        Enum(
            ConversationSender,
            name="conversation_sender",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    sender_user: Mapped[User | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ConversationMessage id={self.id} sender={self.sender_type}>"
