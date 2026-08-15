"""Founder conversation model — org-scoped chat threads with the founder assistant."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.founder_action_proposal import FounderActionProposal
    from app.models.founder_message import FounderMessage


class FounderConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A founder assistant chat thread, org-scoped.

    Conversations are immutable logs of the founder <-> assistant exchange. The
    assistant never writes to org data directly; any action it proposes is
    recorded on a linked :class:`FounderActionProposal`.
    """

    __tablename__ = "founder_conversations"
    __table_args__ = (
        CheckConstraint(
            "title IS NULL OR length(btrim(title)) > 0",
            name="chk_founder_conversations_title_not_blank",
        ),
        Index("idx_founder_conversations_org_created", "organization_id", "created_at"),
        Index(
            "idx_founder_conversations_org_archive",
            "organization_id",
            "is_archived",
            "last_message_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    messages: Mapped[list[FounderMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="FounderMessage.sent_at",
    )
    action_proposals: Mapped[list[FounderActionProposal]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<FounderConversation id={self.id} title={self.title!r}>"
