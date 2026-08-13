"""Lead assignment models: per-org rule + append-only assignment history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AssignmentMethod, AssignmentStrategy

if TYPE_CHECKING:
    from app.models.lead import Lead


class LeadAssignmentRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The auto-assignment strategy for an organization (one per org)."""

    __tablename__ = "lead_assignment_rules"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_lead_assignment_rules_org"),
        CheckConstraint("last_assigned_index >= -1", name="chk_lead_assignment_rules_cursor"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[AssignmentStrategy] = mapped_column(
        Enum(
            AssignmentStrategy,
            name="assignment_strategy",
            native_enum=True,
            validate_strings=True,
        ),
        default=AssignmentStrategy.MANUAL,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Optional restriction to specific assignees; empty list = all sales users.
    target_user_ids: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    # Rule conditions for the RULES strategy, e.g. {"source_ids": [...]}.
    conditions: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    last_assigned_index: Mapped[int] = mapped_column(Integer, default=-1, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LeadAssignmentRule id={self.id} strategy={self.strategy}>"


class LeadAssignmentLog(UUIDPrimaryKeyMixin, Base):
    """Append-only record of a lead changing owner."""

    __tablename__ = "lead_assignment_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    method: Mapped[AssignmentMethod] = mapped_column(
        Enum(
            AssignmentMethod,
            name="assignment_method",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )

    lead: Mapped[Lead] = relationship(back_populates="assignment_logs")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LeadAssignmentLog lead={self.lead_id} to={self.to_user_id}>"
