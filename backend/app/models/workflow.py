"""Workflow model — tenant-scoped workflow registry with execution config."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WorkflowStatus

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.workflow_execution import WorkflowExecution
    from app.models.workflow_trigger import WorkflowTrigger


class Workflow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A workflow definition with execution configuration."""

    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="chk_workflows_name_not_blank"),
        CheckConstraint("version > 0", name="chk_workflows_version_positive"),
        Index("idx_workflows_org_status", "organization_id", "status"),
        Index("idx_workflows_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    definition: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status", native_enum=True, validate_strings=True),
        default=WorkflowStatus.DRAFT,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    execution_mode: Mapped[str] = mapped_column(Text, default="n8n", nullable=False)
    config: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    created_by: Mapped[User] = relationship()
    organization: Mapped[Organization] = relationship(back_populates="workflows")
    triggers: Mapped[list[WorkflowTrigger]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    executions: Mapped[list[WorkflowExecution]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Workflow id={self.id} name={self.name!r} status={self.status}>"