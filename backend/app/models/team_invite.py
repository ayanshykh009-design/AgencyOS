"""TeamInvite model — an invitation to join an organization.

Invites carry a random high-entropy token whose SHA-256 digest is stored
(never the raw token). Acceptance is only possible while the invite is
``pending`` and unexpired; a single accept/reject boundary is enforced in
the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import InviteStatus, UserRole

if TYPE_CHECKING:
    from app.models.user import User


class TeamInvite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A pending (or resolved) invitation to join the organization."""

    __tablename__ = "team_invites"
    __table_args__ = (
        CheckConstraint("length(btrim(email)) > 0", name="chk_team_invites_email_not_blank"),
        CheckConstraint("expires_at > created_at", name="chk_team_invites_expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[InviteStatus] = mapped_column(
        Enum(
            InviteStatus,
            name="invite_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=InviteStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), )
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), )

    invited_by: Mapped[User | None] = relationship(foreign_keys=[invited_by_user_id])

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<TeamInvite id={self.id} email={self.email!r} status={self.status}>"
