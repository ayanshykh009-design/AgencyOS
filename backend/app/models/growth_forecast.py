"""GrowthForecast model — deterministic growth forecasts (org-scoped).

M7 extends the M2 snapshot with the engine columns the deterministic forecast
engines persist: ``method``, the fit history (``base_period_start``/``end``),
the central ``point_estimate`` with ``lower_bound``/``upper_bound``, and the
projected ``series`` plus fit ``errors``. ``total_value``/``confidence_*`` stay
for backward compatibility and mirror the new estimate/bounds.
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
    from app.models.growth_scenario import GrowthScenario
    from app.models.organization import Organization


class GrowthForecast(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A deterministic forecast for a growth metric over a horizon."""

    __tablename__ = "growth_forecasts"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(forecast_type)) > 0",
            name="chk_growth_forecasts_type_not_blank",
        ),
        CheckConstraint("total_value >= 0", name="chk_growth_forecasts_total_nonneg"),
        CheckConstraint("horizon_end >= horizon_start", name="chk_growth_forecasts_horizon_order"),
        CheckConstraint(
            "confidence_low IS NULL OR confidence_high IS NULL "
            "OR confidence_low <= confidence_high",
            name="chk_growth_forecasts_confidence_order",
        ),
        CheckConstraint(
            "method IS NULL OR length(btrim(method)) > 0",
            name="chk_growth_forecasts_method_not_blank",
        ),
        CheckConstraint(
            "base_period_start IS NULL OR base_period_end IS NULL "
            "OR base_period_end >= base_period_start",
            name="chk_growth_forecasts_base_period_order",
        ),
        CheckConstraint(
            "lower_bound IS NULL OR point_estimate IS NULL OR upper_bound IS NULL "
            "OR (lower_bound <= point_estimate AND point_estimate <= upper_bound)",
            name="chk_growth_forecasts_bounds_order",
        ),
        Index(
            "idx_growth_forecasts_org_type_horizon",
            "organization_id",
            "forecast_type",
            "horizon_start",
        ),
        Index("idx_growth_forecasts_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    forecast_type: Mapped[str] = mapped_column(Text, nullable=False)
    horizon_start: Mapped[datetime] = mapped_column(nullable=False)
    horizon_end: Mapped[datetime] = mapped_column(nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    confidence_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    confidence_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    model_config: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    method: Mapped[str | None] = mapped_column(Text)
    base_period_start: Mapped[datetime | None] = mapped_column()
    base_period_end: Mapped[datetime | None] = mapped_column()
    point_estimate: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    series: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    errors: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="growth_forecasts")
    scenarios: Mapped[list[GrowthScenario]] = relationship(back_populates="forecast")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<GrowthForecast id={self.id} type={self.forecast_type!r}>"
