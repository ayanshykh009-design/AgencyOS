"""ExecutionEvent model — append-only per-execution technical timeline.

Records every state-machine transition and worker/adapter/step instrumentation
point for a workflow execution (see ``ExecutionEventType``). Rows are never
updated or deleted by feature code; retention is handled by the dedicated
retention worker (``app/workers/retention_worker.py``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ExecutionEventType

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.workflow import Workflow
    from app.models.workflow_execution import WorkflowExecution


class ExecutionEvent(UUIDPrimaryKeyMixin, Base):
    """An immutable technical timeline entry for a workflow execution."""

    __tablename__ = "execution_events"
    __table_args__ = (
        Index(
            "idx_execution_events_execution_occurred",
            "execution_id",
            "occurred_at",
        ),
        Index(
            "idx_execution_events_org_workflow_occurred",
            "organization_id",
            "workflow_id",
            "occurred_at",
        ),
        Index("idx_execution_events_occurred_at", "occurred_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    event_type: Mapped[ExecutionEventType] = mapped_column(
        Enum(
            ExecutionEventType,
            name="execution_event_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    execution: Mapped[WorkflowExecution] = relationship(back_populates="events")
    workflow: Mapped[Workflow] = relationship()
    organization: Mapped[Organization] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ExecutionEvent execution={self.execution_id} event={self.event_type}>"
