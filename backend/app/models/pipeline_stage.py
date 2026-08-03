"""PipelineStage model — an org-scoped pipeline column (Kanban column).

Seeded default stages mirror the coarse ``lead_status`` lifecycle (open
stages + won/lost), so the existing funnel/dashboard contracts stay intact;
custom stages are an overlay on top of the fixed status enum. Each lifecycle
has exactly one ``is_default`` stage used when a stage is deleted or when a
lead has no explicit stage.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import StageLifecycle

if TYPE_CHECKING:
    from app.models.lead import Lead


class PipelineStage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A labelled pipeline column scoped to an organization."""

    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "lifecycle",
            "name",
            name="uq_pipeline_stages_org_lifecycle_name",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="chk_pipeline_stages_name_not_blank"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle: Mapped[StageLifecycle] = mapped_column(
        Enum(StageLifecycle, name="stage_lifecycle", native_enum=True, validate_strings=True),
        default=StageLifecycle.OPEN,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    leads: Mapped[list[Lead]] = relationship(back_populates="stage")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<PipelineStage id={self.id} name={self.name!r}>"
