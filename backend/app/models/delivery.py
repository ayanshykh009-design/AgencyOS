"""Delivery model — the delivery outbox (org-scoped).

Every outbound founder communication is recorded here first; the delivery
worker moves rows ``queued -> processing -> delivered/failed/cancelled``
(with ``processing -> retrying -> queued`` for scheduled retries) through
the channel provider. ``scheduled_for``/``next_attempt_at`` back the
fair-drain sweep and the per-org pending cap; ``idempotency_key`` makes
enqueue retry-safe; ``notification_id``/``approval_request_id`` link a
delivery to the inbox row it created or the approval gate it announces.

Cooperative cancellation: a PROCESSING delivery is flagged via
``cancel_requested_at``/``cancelled_by_user_id`` and the worker honours the
flag when the provider returns (a successful send always wins). The recovery
sweep uses ``attempt_started_at`` to find stale PROCESSING rows.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DeliveryChannel, DeliveryStatus

if TYPE_CHECKING:
    from app.models.approval_request import ApprovalRequest
    from app.models.delivery_event import DeliveryEvent
    from app.models.notification import Notification
    from app.models.organization import Organization
    from app.models.user import User


class Delivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One outbound communication pending/being sent through a channel."""

    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(subject)) > 0", name="chk_deliveries_subject_not_blank"
        ),
        CheckConstraint(
            "length(btrim(body)) > 0", name="chk_deliveries_body_not_blank"
        ),
        CheckConstraint(
            "attempts >= 0", name="chk_deliveries_attempts_nonneg"
        ),
        CheckConstraint(
            "max_attempts > 0", name="chk_deliveries_max_attempts_positive"
        ),
        CheckConstraint(
            "cancel_requested_at IS NULL OR cancelled_by_user_id IS NOT NULL",
            name="chk_deliveries_cancel_request_has_actor",
        ),
        Index("idx_deliveries_org_status", "organization_id", "status"),
        Index("idx_deliveries_org_created", "organization_id", "created_at"),
        Index(
            "idx_deliveries_org_recipient_status",
            "organization_id",
            "recipient_user_id",
            "status",
        ),
        Index(
            "idx_deliveries_queued_next_attempt",
            "next_attempt_at",
            postgresql_where="status IN ('queued', 'processing')",
        ),
        Index(
            "idx_deliveries_retrying_next_attempt",
            "next_attempt_at",
            postgresql_where="status = 'retrying'",
        ),
        Index(
            "idx_deliveries_processing_attempt_started",
            "attempt_started_at",
            postgresql_where="status = 'processing'",
        ),
        Index(
            "uq_deliveries_org_idempotency",
            "organization_id",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
        Index("idx_deliveries_approval_request", "approval_request_id"),
        Index("idx_deliveries_notification", "notification_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[DeliveryChannel] = mapped_column(
        Enum(
            DeliveryChannel,
            name="delivery_channel",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("notifications.id", ondelete="SET NULL")
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="SET NULL")
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(
            DeliveryStatus,
            name="delivery_status",
            native_enum=True,
            validate_strings=True,
        ),
        default=DeliveryStatus.QUEUED,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=4, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column()
    attempt_started_at: Mapped[datetime | None] = mapped_column()
    cancel_requested_at: Mapped[datetime | None] = mapped_column()
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    payload: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column()
    scheduled_for: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column()
    failed_at: Mapped[datetime | None] = mapped_column()
    cancelled_at: Mapped[datetime | None] = mapped_column()

    organization: Mapped[Organization] = relationship(back_populates="deliveries")
    recipient: Mapped[User | None] = relationship(
        foreign_keys=[recipient_user_id]
    )
    notification: Mapped[Notification | None] = relationship()
    approval_request: Mapped[ApprovalRequest | None] = relationship()
    events: Mapped[list[DeliveryEvent]] = relationship(
        back_populates="delivery", order_by="DeliveryEvent.occurred_at"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Delivery id={self.id} channel={self.channel} status={self.status}>"
