"""DeliveryEvent model — append-only per-delivery timeline.

Records every state-machine transition for a delivery (see
``DeliveryEventType``). Rows are never updated or deleted by feature code.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import DeliveryEventType

if TYPE_CHECKING:
    from app.models.delivery import Delivery
    from app.models.organization import Organization


class DeliveryEvent(UUIDPrimaryKeyMixin, Base):
    """An immutable timeline entry for a delivery."""

    __tablename__ = "delivery_events"
    __table_args__ = (
        Index(
            "idx_delivery_events_delivery_occurred",
            "delivery_id",
            "occurred_at",
        ),
        Index(
            "idx_delivery_events_org_occurred",
            "organization_id",
            "occurred_at",
        ),
        Index("idx_delivery_events_occurred", "occurred_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[DeliveryEventType] = mapped_column(
        Enum(
            DeliveryEventType,
            name="delivery_event_type",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    delivery: Mapped[Delivery] = relationship(back_populates="events")
    organization: Mapped[Organization] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<DeliveryEvent delivery={self.delivery_id} event={self.event_type}>"
