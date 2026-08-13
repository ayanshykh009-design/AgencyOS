"""GrowthHealthWeight model — configurable, versioned health weights (M7).

Exactly one version may be active per organization (partial unique index in
the DDL); when no active row exists the growth service falls back to the
built-in default weights. Each ``growth_analyses`` row copies the weights it
was computed with, so retuning never disturbs historical snapshots.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class GrowthHealthWeight(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A versioned set of business-health weights for an organization."""

    __tablename__ = "growth_health_weights"
    __table_args__ = (
        CheckConstraint("version > 0", name="chk_growth_health_weights_version_positive"),
        CheckConstraint(
            "jsonb_typeof(weights) = 'object'",
            name="chk_growth_health_weights_weights_object",
        ),
        Index("idx_growth_health_weights_org_version", "organization_id", "version"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    weights: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    organization: Mapped[Organization] = relationship(back_populates="growth_health_weights")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<GrowthHealthWeight org={self.organization_id} "
            f"v{self.version} active={self.is_active}>"
        )
