"""LeadSource model — where leads come from (per organization)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OutreachChannel

if TYPE_CHECKING:
    from app.models.lead import Lead


class LeadSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A labelled source of leads scoped to an organization."""

    __tablename__ = "lead_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_lead_sources_org_name"),
        CheckConstraint("length(btrim(name)) > 0", name="chk_lead_sources_name_not_blank"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[OutreachChannel] = mapped_column(
        Enum(OutreachChannel, name="outreach_channel", native_enum=True, validate_strings=True),
        default=OutreachChannel.CONTACT_FORM,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    leads: Mapped[list[Lead]] = relationship(back_populates="lead_source")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<LeadSource id={self.id} name={self.name!r}>"
