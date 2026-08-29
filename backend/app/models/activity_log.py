"""ActivityLog model — append-only business audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ActivityEventType

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.user import User


class ActivityLog(UUIDPrimaryKeyMixin, Base):
    """An immutable audit record of a business event (append-only)."""

    __tablename__ = "activity_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))
    event_type: Mapped[ActivityEventType] = mapped_column(
        Enum(
            ActivityEventType,
            name="activity_event_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped[User | None] = relationship()
    lead: Mapped[Lead | None] = relationship(back_populates="activity_logs")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ActivityLog id={self.id} event={self.event_type}>"
