"""User model — agency team member scoped to one organization."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.credential import Credential
    from app.models.notification import Notification
    from app.models.organization import Organization
    from app.models.workflow import Workflow
    from app.models.workflow_execution import WorkflowExecution


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user account. Phase 2 added first-party auth (password_hash)."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        CheckConstraint(
            "email = lower(btrim(email)) AND email LIKE '%_@_%'",
            name="chk_users_email_normalized",
        ),
        CheckConstraint("length(btrim(full_name)) > 0", name="chk_users_full_name_not_blank"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True, validate_strings=True),
        default=UserRole.MEMBER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column()

    organization: Mapped[Organization] = relationship(back_populates="users")
    created_workflows: Mapped[list[Workflow]] = relationship(back_populates="created_by")
    requested_executions: Mapped[list[WorkflowExecution]] = relationship(
        back_populates="requested_by",
        foreign_keys="WorkflowExecution.requested_by_user_id",
    )
    created_credentials: Mapped[list[Credential]] = relationship(back_populates="created_by")
    notifications: Mapped[list[Notification]] = relationship(back_populates="user")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r}>"
