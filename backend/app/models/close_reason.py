"""CloseReason model — a labelled reason for closing a lead as won or lost."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import StageLifecycle


class CloseReason(UUIDPrimaryKeyMixin, Base):
    """A won/lost close reason scoped to an organization (append + delete)."""

    __tablename__ = "close_reasons"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "lifecycle",
            "name",
            name="uq_close_reasons_org_lifecycle_name",
        ),
        CheckConstraint("length(btrim(name)) > 0", name="chk_close_reasons_name_not_blank"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lifecycle: Mapped[StageLifecycle] = mapped_column(
        Enum(StageLifecycle, name="stage_lifecycle", native_enum=True, validate_strings=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<CloseReason id={self.id} name={self.name!r}>"
