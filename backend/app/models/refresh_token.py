"""RefreshToken model — rotation-based refresh token storage.

Only the SHA-256 digest of the opaque token is persisted; the raw token is
returned to the client exactly once and never stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """A single refresh-token record (one row per issued token)."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        CheckConstraint("expires_at > created_at", name="chk_refresh_tokens_expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column()
    replaced_by: Mapped[uuid.UUID | None] = mapped_column()

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<RefreshToken id={self.id} revoked={self.revoked_at is not None}>"
