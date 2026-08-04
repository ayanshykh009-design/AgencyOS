"""WorkflowExecution model — execution queue + history with retry tracking."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExecutionStatus

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.workflow import Workflow
    from app.models.workflow_trigger import WorkflowTrigger


class WorkflowExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single execution of a workflow (queued, running, completed, etc.)."""

    __tablename__ = "workflow_executions"
    __table_args__ = (
        CheckConstraint(
            "attempts >= 0", name="chk_workflow_executions_attempts_nonneg"
        ),
        CheckConstraint(
            "max_attempts > 0", name="chk_workflow_executions_max_attempts_positive"
        ),
        CheckConstraint(
            "retry_delay_seconds >= 0",
            name="chk_workflow_executions_retry_delay_nonneg",
        ),
        CheckConstraint(
            "retry_backoff IN ('constant','exponential')",
            name="chk_workflow_executions_retry_backoff",
        ),
        Index("idx_workflow_executions_org_status", "organization_id", "status"),
        Index("idx_workflow_executions_org_workflow", "organization_id", "workflow_id"),
        Index(
            "idx_workflow_executions_next_retry",
            "next_retry_at",
            postgresql_where="status = 'retrying'",
        ),
        Index(
            "idx_workflow_executions_trace_id",
            "trace_id",
            postgresql_where="trace_id IS NOT NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_triggers.id", ondelete="SET NULL")
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="execution_status", native_enum=True, validate_strings=True),
        default=ExecutionStatus.QUEUED,
        nullable=False,
    )
    input: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    output: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    retry_delay_seconds: Mapped[int] = mapped_column(default=60, nullable=False)
    retry_backoff: Mapped[str] = mapped_column(default="exponential", nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column()
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    trace_id: Mapped[uuid.UUID | None] = mapped_column()

    workflow: Mapped[Workflow] = relationship(back_populates="executions")
    trigger: Mapped[WorkflowTrigger | None] = relationship(back_populates="executions")
    organization: Mapped[Organization] = relationship(back_populates="workflow_executions")
    requested_by: Mapped[User | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WorkflowExecution id={self.id} workflow={self.workflow_id} status={self.status}>"