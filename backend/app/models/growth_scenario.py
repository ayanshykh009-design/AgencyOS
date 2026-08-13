"""GrowthScenario model — saved what-if projection (org-scoped, M7).

``assumption_deltas`` are the parameter deltas applied to a forecast (or to
the live pipeline when ``forecast_id`` is NULL); ``result`` is the projected
values the deterministic scenario engine computed.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.growth_forecast import GrowthForecast
    from app.models.organization import Organization


class GrowthScenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A saved deterministic scenario projection for an organization."""

    __tablename__ = "growth_scenarios"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="chk_growth_scenarios_name_not_blank"),
        CheckConstraint(
            "jsonb_typeof(assumption_deltas) = 'object'",
            name="chk_growth_scenarios_assumptions_object",
        ),
        CheckConstraint(
            "jsonb_typeof(result) = 'object'",
            name="chk_growth_scenarios_result_object",
        ),
        Index("idx_growth_scenarios_org_created", "organization_id", "created_at"),
        Index("idx_growth_scenarios_forecast", "forecast_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    forecast_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("growth_forecasts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assumption_deltas: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    result: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    organization: Mapped[Organization] = relationship(back_populates="growth_scenarios")
    forecast: Mapped[GrowthForecast | None] = relationship(back_populates="scenarios")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<GrowthScenario id={self.id} name={self.name!r}>"
