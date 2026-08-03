"""Note model — free-form commentary attached to a lead.

Notes are always lead-scoped (``lead_id`` is required) so the timeline is
easy to reconstruct; the author is recorded for accountability. Pinning lets
teams highlight the important context at the top of a lead.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.user import User


class Note(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A comment on a lead authored by a team member."""

    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint("length(btrim(body)) > 0", name="chk_notes_body_not_blank"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    lead: Mapped[Lead] = relationship(back_populates="lead_notes")
    author: Mapped[User | None] = relationship(foreign_keys=[author_user_id])

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Note id={self.id} lead={self.lead_id} pinned={self.pinned}>"
