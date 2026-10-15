"""AuthToken model — single-use, hashed email-verification / password-reset tokens.

Only the SHA-256 digest of the opaque token is persisted; the raw token is
delivered to the user (email link) exactly once and never stored. Rows are
tenant-isolated through the owning user (see 0036_account_lifecycle.sql).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User

# Token purposes (kept in sync with the CHECK constraint in 0036).
PURPOSE_EMAIL_VERIFICATION = "email_verification"
PURPOSE_PASSWORD_RESET = "password_reset"


class AuthToken(UUIDPrimaryKeyMixin, Base):
    """A single one-time token row (email verification or password reset)."""

    __tablename__ = "auth_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('email_verification', 'password_reset')",
            name="chk_auth_tokens_purpose",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AuthToken id={self.id} purpose={self.purpose!r} used={self.used_at is not None}>"
