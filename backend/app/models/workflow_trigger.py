"""WorkflowTrigger model — how a workflow is triggered (manual/event/schedule)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WorkflowTriggerType

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.workflow import Workflow
    from app.models.workflow_execution import WorkflowExecution


class WorkflowTrigger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A trigger that can start a workflow execution."""

    __tablename__ = "workflow_triggers"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="chk_workflow_triggers_name_not_blank"),
        Index("idx_workflow_triggers_org_workflow", "organization_id", "workflow_id"),
        Index(
            "idx_workflow_triggers_event_type",
            "event_type",
            postgresql_where="event_type IS NOT NULL",
        ),
        Index(
            "idx_workflow_triggers_schedule_due",
            "last_fired_at",
            postgresql_where="trigger_type = 'schedule' AND enabled",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_type: Mapped[WorkflowTriggerType] = mapped_column(
        Enum(
            WorkflowTriggerType,
            name="workflow_trigger_type",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    event_type: Mapped[str | None] = mapped_column(Text)
    schedule_cron: Mapped[str | None] = mapped_column(Text)
    # Last dispatch timestamp (UTC). NULL until the first successful dispatch;
    # used for idempotent cron-tick dedup across worker instances/restarts.
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    workflow: Mapped[Workflow] = relationship(back_populates="triggers")
    organization: Mapped[Organization] = relationship(back_populates="workflow_triggers")
    executions: Mapped[list[WorkflowExecution]] = relationship(back_populates="trigger")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WorkflowTrigger id={self.id} name={self.name!r} type={self.trigger_type}>"
