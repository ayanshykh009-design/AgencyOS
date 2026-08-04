"""WorkflowEvent model — append-only event log for trigger matching."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class WorkflowEvent(UUIDPrimaryKeyMixin, Base):
    """An event published for trigger matching (append-only log)."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        CheckConstraint("length(btrim(event_type)) > 0", name="chk_workflow_events_type_not_blank"),
        Index("idx_workflow_events_org_type", "organization_id", "event_type"),
        Index(
            "idx_workflow_events_org_consumed",
            "organization_id",
            "consumed",
            postgresql_where="consumed = false",
        ),
        Index("idx_workflow_events_occurred", "occurred_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    consumed: Mapped[bool] = mapped_column(default=False, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, index=True)

    organization: Mapped[Organization] = relationship(back_populates="workflow_events")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WorkflowEvent id={self.id} type={self.event_type!r} consumed={self.consumed}>"