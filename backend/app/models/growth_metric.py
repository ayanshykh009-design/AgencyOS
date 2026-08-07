"""GrowthMetric model — periodized growth/performance rows (org-scoped).

Rows are pruned after ``GROWTH_METRICS_RETENTION_DAYS`` (36 months) by the
retention sweep on ``recorded_at``. One row per (org, metric_type, period).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class GrowthMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single periodized growth/performance measurement."""

    __tablename__ = "growth_metrics"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(metric_type)) > 0",
            name="chk_growth_metrics_type_not_blank",
        ),
        CheckConstraint("value >= 0", name="chk_growth_metrics_value_nonneg"),
        CheckConstraint(
            "period_end >= period_start", name="chk_growth_metrics_period_order"
        ),
        Index(
            "uq_growth_metrics_org_type_period",
            "organization_id",
            "metric_type",
            "period_start",
            "period_end",
            unique=True,
        ),
        Index(
            "idx_growth_metrics_org_type_recorded",
            "organization_id",
            "metric_type",
            "recorded_at",
        ),
        Index("idx_growth_metrics_recorded_retention", "recorded_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_type: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[datetime] = mapped_column(nullable=False)
    period_end: Mapped[datetime] = mapped_column(nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="growth_metrics")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<GrowthMetric id={self.id} type={self.metric_type!r} value={self.value}>"
