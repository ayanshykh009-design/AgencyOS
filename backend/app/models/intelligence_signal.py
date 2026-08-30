"""IntelligenceSignal model — deterministic, scored triage signal (M9).

M9 is the triage/orchestration layer: it never recomputes growth metrics. It
materializes a single, deduplicated, scored feed over M7/M8 output
(``growth_recommendations``, ``business_insights``, ``growth_analyses``
findings) and bounded pipeline condition detectors. Every row carries a
versioned ``priority_score`` (weighted sum in ``priority_components``) plus
handoff fields (``last_notified_at``, ``acknowledged_*``) so the worker can
notify exactly once and the UI can reason about the full lifecycle.

``content_hash`` is deterministic per source row; the partial unique index
``(organization_id, content_hash) WHERE status <> 'superseded'`` guarantees at
most one live signal per source. ``source_type`` / ``source_row_id`` is the
polymorphic lineage back to the M7/M8 row that produced the signal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    IntelligenceConfidence,
    IntelligenceSignalSeverity,
    IntelligenceSignalStatus,
    SignalCategory,
    SignalSourceType,
)

if TYPE_CHECKING:
    from app.models.organization import Organization


class IntelligenceSignal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A deterministic, scored business signal surfaced to a founder."""

    __tablename__ = "intelligence_signals"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(title)) > 0", name="chk_intelligence_signals_title_not_blank"
        ),
        CheckConstraint(
            "length(btrim(summary)) > 0", name="chk_intelligence_signals_summary_not_blank"
        ),
        CheckConstraint(
            "length(btrim(content_hash)) > 0",
            name="chk_intelligence_signals_hash_not_blank",
        ),
        CheckConstraint(
            "priority_score >= 0 AND priority_score <= 1",
            name="chk_intelligence_signals_priority_range",
        ),
        Index(
            "idx_intelligence_signals_org_status_priority",
            "organization_id",
            "status",
            "priority_score",
        ),
        Index(
            "idx_intelligence_signals_org_source",
            "organization_id",
            "source_type",
            "source_row_id",
            postgresql_where="source_row_id IS NOT NULL",
        ),
        Index("idx_intelligence_signals_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    signal_category: Mapped[SignalCategory] = mapped_column(
        Enum(
            SignalCategory,
            name="signal_category",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    source_type: Mapped[SignalSourceType] = mapped_column(
        Enum(
            SignalSourceType,
            name="signal_source_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    source_row_id: Mapped[uuid.UUID | None] = mapped_column()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[IntelligenceSignalSeverity] = mapped_column(
        Enum(
            IntelligenceSignalSeverity,
            name="intelligence_signal_severity",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=IntelligenceSignalSeverity.INFO,
        nullable=False,
    )
    business_impact: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    priority_score: Mapped[float] = mapped_column(
        Numeric(5, 4), default=0, server_default="0", nullable=False
    )
    priority_components: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    recommended_next_step: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[IntelligenceConfidence] = mapped_column(
        Enum(
            IntelligenceConfidence,
            name="intelligence_confidence",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=IntelligenceConfidence.LOW,
        nullable=False,
    )
    status: Mapped[IntelligenceSignalStatus] = mapped_column(
        Enum(
            IntelligenceSignalStatus,
            name="intelligence_signal_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=IntelligenceSignalStatus.ACTIVE,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), )
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), )
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), )

    organization: Mapped[Organization] = relationship(back_populates="intelligence_signals")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<IntelligenceSignal id={self.id} category={self.signal_category} "
            f"priority={self.priority_score} status={self.status}>"
        )
