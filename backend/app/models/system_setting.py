"""SystemSetting model — operator-controlled key/value settings (instance-global).

Used by the automation kill switch (``automation.control``) and any future
operator setting. Values are stored as JSONB so a single table serves booleans,
strings, and structured metadata alike.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SystemSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One operator setting keyed by a unique string."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<SystemSetting key={self.key}>"
