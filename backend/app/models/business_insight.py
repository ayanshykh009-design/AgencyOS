"""BusinessInsight model — generated business insight rows (org-scoped).

``source_table`` / ``source_row_id`` is an optional polymorphic reference to
the domain row an insight derives from (lead, workflow, metric, ...).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import InsightSeverity, InsightStatus, InsightType

if TYPE_CHECKING:
    from app.models.organization import Organization


class BusinessInsight(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A generated business insight for a founder, org-scoped."""

    __tablename__ = "business_insights"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="chk_business_insights_title_not_blank"),
        CheckConstraint(
            "length(btrim(summary)) > 0", name="chk_business_insights_summary_not_blank"
        ),
        CheckConstraint(
            "source_table IS NULL OR length(btrim(source_table)) > 0",
            name="chk_business_insights_source_table_not_blank",
        ),
        Index("idx_business_insights_org_status", "organization_id", "status"),
        Index("idx_business_insights_org_type", "organization_id", "insight_type"),
        Index("idx_business_insights_org_created", "organization_id", "created_at"),
        Index(
            "idx_business_insights_source",
            "source_table",
            "source_row_id",
            postgresql_where="source_row_id IS NOT NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    insight_type: Mapped[InsightType] = mapped_column(
        Enum(
            InsightType,
            name="insight_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    severity: Mapped[InsightSeverity] = mapped_column(
        Enum(
            InsightSeverity,
            name="insight_severity",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=InsightSeverity.INFO,
        nullable=False,
    )
    status: Mapped[InsightStatus] = mapped_column(
        Enum(
            InsightStatus,
            name="insight_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=InsightStatus.ACTIVE,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_table: Mapped[str | None] = mapped_column(Text)
    source_row_id: Mapped[uuid.UUID | None] = mapped_column()
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="business_insights")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<BusinessInsight id={self.id} type={self.insight_type} title={self.title!r}>"
