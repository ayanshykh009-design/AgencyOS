"""AgentState model — per-agent health/status bookkeeping for the agent runtime.

One row per (organization, agent_name), maintained by the runtime as runs
complete. Aggregate counters (queue_depth, total_runs, averages) are
server-side rolling values; they are never client-computed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AgentHealth, AgentStateStatus

if TYPE_CHECKING:
    from app.models.organization import Organization


class AgentState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Upserted health/status row for one agent within an organization."""

    __tablename__ = "agent_state"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(agent_name)) > 0", name="chk_agent_state_agent_name_not_blank"
        ),
        CheckConstraint("queue_depth >= 0", name="chk_agent_state_queue_depth_nonneg"),
        CheckConstraint("total_runs >= 0", name="chk_agent_state_total_runs_nonneg"),
        CheckConstraint("average_runtime_ms >= 0", name="chk_agent_state_avg_runtime_nonneg"),
        CheckConstraint("average_cost >= 0", name="chk_agent_state_avg_cost_nonneg"),
        Index("uq_agent_state_org_agent", "organization_id", "agent_name", unique=True),
        Index("idx_agent_state_status_health", "status", "health"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AgentStateStatus] = mapped_column(
        Enum(
            AgentStateStatus,
            name="agent_state_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=AgentStateStatus.ACTIVE,
        nullable=False,
    )
    health: Mapped[AgentHealth] = mapped_column(
        Enum(
            AgentHealth,
            name="agent_health",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=AgentHealth.HEALTHY,
        nullable=False,
    )
    queue_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_runtime_ms: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0", nullable=False
    )
    average_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0", nullable=False
    )
    last_execution: Mapped[datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization] = relationship(back_populates="agent_states")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AgentState id={self.id} agent={self.agent_name!r} health={self.health}>"
