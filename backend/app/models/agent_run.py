"""AgentRun model — per-run execution records for the agent runtime.

Rows are pruned after ``AGENT_RUN_RETENTION_DAYS`` by the retention sweep on
``created_at``. ``output`` / ``error`` / ``duration_ms`` / ``cost`` are filled
by the runtime as a run progresses.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AgentRunStatus, AgentRunTrigger

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.workflow import Workflow


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of an agent, org-scoped."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(agent_name)) > 0", name="chk_agent_runs_agent_name_not_blank"
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="chk_agent_runs_duration_nonneg",
        ),
        CheckConstraint("cost >= 0", name="chk_agent_runs_cost_nonneg"),
        Index("idx_agent_runs_org_status", "organization_id", "status"),
        Index(
            "idx_agent_runs_org_agent_created",
            "organization_id",
            "agent_name",
            "created_at",
        ),
        Index("idx_agent_runs_org_created", "organization_id", "created_at"),
        Index("idx_agent_runs_org_workflow", "organization_id", "workflow_id"),
        Index("idx_agent_runs_created_retention", "created_at"),
        Index(
            "uq_agent_runs_org_idempotency",
            "organization_id",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
        Index(
            "idx_agent_runs_cancel_pending",
            "cancel_requested_at",
            postgresql_where="cancel_requested_at IS NOT NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agent_run_status", native_enum=True, validate_strings=True),
        default=AgentRunStatus.QUEUED,
        nullable=False,
    )
    trigger: Mapped[AgentRunTrigger] = mapped_column(
        Enum(AgentRunTrigger, name="agent_run_trigger", native_enum=True, validate_strings=True),
        default=AgentRunTrigger.MANUAL,
        nullable=False,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL")
    )
    input: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
    cancel_requested_at: Mapped[datetime | None] = mapped_column()
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str | None] = mapped_column()

    organization: Mapped[Organization] = relationship(back_populates="agent_runs")
    workflow: Mapped[Workflow | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AgentRun id={self.id} agent={self.agent_name!r} status={self.status}>"
