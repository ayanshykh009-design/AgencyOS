"""GrowthAnalysis model — deterministic analysis snapshot (org-scoped, M7).

One row per engine run. ``details`` carries the engine's structured output;
``evidence`` lists the concrete data points each finding rests on so
recommendations stay traceable; ``weights`` is the weight set the health score
used (empty for non-health analyses).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import GrowthAnalysisStatus, GrowthAnalysisType

if TYPE_CHECKING:
    from app.models.organization import Organization


class GrowthAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A persisted deterministic growth analysis for an organization."""

    __tablename__ = "growth_analyses"
    __table_args__ = (
        CheckConstraint("length(btrim(summary)) > 0", name="chk_growth_analyses_summary_not_blank"),
        CheckConstraint("period_end >= period_start", name="chk_growth_analyses_period_order"),
        CheckConstraint(
            "health_score IS NULL OR (health_score >= 0 AND health_score <= 100)",
            name="chk_growth_analyses_health_range",
        ),
        CheckConstraint(
            "length(btrim(generated_by)) > 0",
            name="chk_growth_analyses_generated_by_not_blank",
        ),
        Index("idx_growth_analyses_org_created", "organization_id", "created_at"),
        Index(
            "idx_growth_analyses_org_type_created",
            "organization_id",
            "analysis_type",
            "created_at",
        ),
        Index(
            "idx_growth_analyses_org_status_created",
            "organization_id",
            "status",
            "created_at",
        ),
        Index(
            "idx_growth_analyses_org_period",
            "organization_id",
            "period_start",
            "period_end",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_type: Mapped[GrowthAnalysisType] = mapped_column(
        Enum(
            GrowthAnalysisType, name="growth_analysis_type", native_enum=True, validate_strings=True
        ),
        nullable=False,
    )
    status: Mapped[GrowthAnalysisStatus] = mapped_column(
        Enum(
            GrowthAnalysisStatus,
            name="growth_analysis_status",
            native_enum=True,
            validate_strings=True,
        ),
        default=GrowthAnalysisStatus.COMPLETED,
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(nullable=False)
    period_end: Mapped[datetime] = mapped_column(nullable=False)
    health_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    weights: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    metrics_used: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(
        Text, default="agent", server_default="agent", nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="growth_analyses")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<GrowthAnalysis id={self.id} type={self.analysis_type!r}>"
