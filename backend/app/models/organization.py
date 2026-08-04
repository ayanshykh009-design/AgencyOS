"""Organization model — the multi-tenancy root."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.credential import Credential
    from app.models.user import User
    from app.models.workflow import Workflow
    from app.models.workflow_event import WorkflowEvent
    from app.models.workflow_execution import WorkflowExecution
    from app.models.workflow_trigger import WorkflowTrigger


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An agency tenant. All tenant-scoped rows reference ``organization_id``."""

    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        CheckConstraint("length(btrim(name)) > 0", name="chk_organizations_name_not_blank"),
        CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]*$'", name="chk_organizations_slug_format"
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    website: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    settings: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    users: Mapped[list[User]] = relationship(back_populates="organization")
    workflows: Mapped[list[Workflow]] = relationship(back_populates="organization")
    workflow_triggers: Mapped[list[WorkflowTrigger]] = relationship(back_populates="organization")
    workflow_executions: Mapped[list[WorkflowExecution]] = relationship(
        back_populates="organization"
    )
    workflow_events: Mapped[list[WorkflowEvent]] = relationship(back_populates="organization")
    credentials: Mapped[list[Credential]] = relationship(back_populates="organization")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Organization id={self.id} slug={self.slug!r}>"
