"""ApprovalLog model — immutable audit trail of approval decisions.

Append-only: rows are created once and never updated or deleted (no
``updated_at`` column, no update/delete RLS policies). Mirrors the
``ExecutionEvent`` append-only pattern.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import ApprovalLogAction

if TYPE_CHECKING:
    from app.models.approval_request import ApprovalRequest
    from app.models.organization import Organization
    from app.models.user import User


class ApprovalLog(UUIDPrimaryKeyMixin, Base):
    """One immutable approval lifecycle entry."""

    __tablename__ = "approval_logs"
    __table_args__ = (
        Index("idx_approval_logs_request_occurred", "approval_request_id", "occurred_at"),
        Index("idx_approval_logs_org_occurred", "organization_id", "occurred_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[ApprovalLogAction] = mapped_column(
        Enum(
            ApprovalLogAction,
            name="approval_log_action",
            native_enum=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="approval_logs")
    approval_request: Mapped[ApprovalRequest] = relationship(back_populates="logs")
    actor: Mapped[User | None] = relationship(foreign_keys=[actor_user_id])

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ApprovalLog id={self.id} action={self.action}>"
