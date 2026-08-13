"""Notification model — in-app notification inbox rows (org-scoped).

Rows are pruned after ``NOTIFICATION_RETENTION_DAYS`` by the retention sweep
on ``created_at``. ``read_at`` / ``is_read`` mark manual acknowledgement.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import NotificationType

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An in-app notification row in a per-user inbox, org-scoped."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="chk_notifications_title_not_blank"),
        CheckConstraint("length(btrim(body)) > 0", name="chk_notifications_body_not_blank"),
        Index("idx_notifications_org_user_read", "organization_id", "user_id", "is_read"),
        Index(
            "idx_notifications_user_unread",
            "user_id",
            postgresql_where="is_read = false",
        ),
        Index("idx_notifications_org_created", "organization_id", "created_at"),
        Index("idx_notifications_created_retention", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type", native_enum=True, validate_strings=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column()
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="notifications")
    user: Mapped[User | None] = relationship(back_populates="notifications")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Notification id={self.id} type={self.type} title={self.title!r}>"
