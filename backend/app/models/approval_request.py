"""ApprovalRequest model — workflow-gated approval requests (org-scoped).

Pending requests auto-expire (deny) at ``expires_at``; the default matches
``APPROVAL_EXPIRY_HOURS`` (24h). Decisions are mirrored into the immutable
``approval_logs`` audit trail.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ApprovalRequestStatus

if TYPE_CHECKING:
    from app.models.approval_log import ApprovalLog
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.workflow import Workflow
    from app.models.workflow_execution import WorkflowExecution


class ApprovalRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A pending approval gate for a workflow action, org-scoped."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(title)) > 0", name="chk_approval_requests_title_not_blank"
        ),
        Index("idx_approval_requests_org_status", "organization_id", "status"),
        Index(
            "idx_approval_requests_org_approver_status",
            "organization_id",
            "approver_user_id",
            "status",
        ),
        Index("idx_approval_requests_org_created", "organization_id", "created_at"),
        Index(
            "idx_approval_requests_pending_expiry",
            "expires_at",
            postgresql_where="status = 'pending'",
        ),
        Index("idx_approval_requests_execution", "workflow_execution_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL")
    )
    workflow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="SET NULL")
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ApprovalRequestStatus] = mapped_column(
        Enum(
            ApprovalRequestStatus,
            name="approval_request_status",
            native_enum=True,
            validate_strings=True,
        ),
        default=ApprovalRequestStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        server_default=text("now() + interval '24 hours'"), nullable=False
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column()
    decision_note: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization] = relationship(back_populates="approval_requests")
    workflow: Mapped[Workflow | None] = relationship()
    workflow_execution: Mapped[WorkflowExecution | None] = relationship()
    requested_by: Mapped[User | None] = relationship(
        foreign_keys=[requested_by_user_id]
    )
    approver: Mapped[User | None] = relationship(foreign_keys=[approver_user_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_user_id])
    logs: Mapped[list[ApprovalLog]] = relationship(back_populates="approval_request")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ApprovalRequest id={self.id} status={self.status} title={self.title!r}>"
