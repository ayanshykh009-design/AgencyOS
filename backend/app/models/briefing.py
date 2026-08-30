"""Briefing model — generated founder briefings (daily/weekly/manual), org-scoped."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BriefingType

if TYPE_CHECKING:
    from app.models.organization import Organization


class Briefing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A generated founder briefing snapshot, org-scoped."""

    __tablename__ = "briefings"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="chk_briefings_title_not_blank"),
        CheckConstraint("length(btrim(summary)) > 0", name="chk_briefings_summary_not_blank"),
        Index("idx_briefings_org_type_created", "organization_id", "briefing_type", "created_at"),
        Index("idx_briefings_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    briefing_type: Mapped[BriefingType] = mapped_column(
        Enum(
            BriefingType,
            name="briefing_type",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=BriefingType.DAILY,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="briefings")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Briefing id={self.id} type={self.briefing_type} title={self.title!r}>"
