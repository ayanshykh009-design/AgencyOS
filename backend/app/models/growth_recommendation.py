"""GrowthRecommendation model — evidence-backed recommendation (org-scoped, M7).

Every recommendation carries ``evidence`` (concrete data points) and a
qualitative ``confidence`` (high/medium/low). ``source_analysis_id`` links back
to the ``growth_analyses`` row that produced it so the UI can trace reasoning.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RecommendationPriority, RecommendationStatus

if TYPE_CHECKING:
    from app.models.growth_analysis import GrowthAnalysis
    from app.models.organization import Organization


class GrowthRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A deterministic, evidence-linked growth recommendation."""

    __tablename__ = "growth_recommendations"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(recommendation_type)) > 0",
            name="chk_growth_recommendations_type_not_blank",
        ),
        CheckConstraint(
            "length(btrim(title)) > 0",
            name="chk_growth_recommendations_title_not_blank",
        ),
        CheckConstraint(
            "length(btrim(summary)) > 0",
            name="chk_growth_recommendations_summary_not_blank",
        ),
        CheckConstraint(
            "action_type IS NULL OR length(btrim(action_type)) > 0",
            name="chk_growth_recommendations_action_type_not_blank",
        ),
        Index("idx_growth_recommendations_org_status", "organization_id", "status"),
        Index("idx_growth_recommendations_org_created", "organization_id", "created_at"),
        Index("idx_growth_recommendations_org_priority", "organization_id", "priority"),
        Index("idx_growth_recommendations_analysis", "source_analysis_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recommendation_type: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[RecommendationPriority] = mapped_column(
        Enum(
            RecommendationPriority,
            name="recommendation_priority",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecommendationPriority.MEDIUM,
        nullable=False,
    )
    confidence: Mapped[RecommendationPriority] = mapped_column(
        Enum(
            RecommendationPriority,
            name="recommendation_priority",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecommendationPriority.MEDIUM,
        nullable=False,
    )
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(
            RecommendationStatus,
            name="recommendation_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecommendationStatus.ACTIVE,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str | None] = mapped_column(Text)
    action_payload: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    source_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("growth_analyses.id", ondelete="SET NULL")
    )
    evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="growth_recommendations")
    source_analysis: Mapped[GrowthAnalysis | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<GrowthRecommendation id={self.id} type={self.recommendation_type!r} "
            f"title={self.title!r}>"
        )
