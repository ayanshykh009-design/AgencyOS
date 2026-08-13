"""ProviderUsage model — per-day token/request accounting per provider."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class ProviderUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Daily usage rollup for an external provider. No credentials stored."""

    __tablename__ = "provider_usage"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "feature",
            "usage_date",
            name="uq_provider_usage_daily",
        ),
        CheckConstraint("length(btrim(provider)) > 0", name="chk_provider_usage_provider"),
        CheckConstraint("length(btrim(feature)) > 0", name="chk_provider_usage_feature"),
        CheckConstraint("request_count >= 0", name="chk_provider_usage_requests"),
        CheckConstraint("input_tokens >= 0", name="chk_provider_usage_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="chk_provider_usage_output_tokens"),
        CheckConstraint("cost_usd >= 0", name="chk_provider_usage_cost"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )

    organization: Mapped[Organization] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ProviderUsage id={self.id} provider={self.provider!r}>"
