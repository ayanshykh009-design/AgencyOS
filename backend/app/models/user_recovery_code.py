"""UserRecoveryCode model — one-time MFA recovery codes (hashed at rest)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserRecoveryCode(UUIDPrimaryKeyMixin, Base):
    """A single hashed recovery code (Argon2id; verified by scanning unused rows)."""

    __tablename__ = "user_recovery_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<UserRecoveryCode id={self.id} used={self.used_at is not None}>"
