"""ImportRowError model — append-only per-row import failures."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.import_job import ImportJob


class ImportRowError(UUIDPrimaryKeyMixin, Base):
    """A rejected row from an import job (append-only)."""

    __tablename__ = "import_row_errors"
    __table_args__ = (
        CheckConstraint("row_number >= 1", name="chk_import_row_errors_row_number"),
        CheckConstraint("length(btrim(error_code)) > 0", name="chk_import_row_errors_code"),
        CheckConstraint("length(btrim(error_message)) > 0", name="chk_import_row_errors_message"),
    )

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_row: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    import_job: Mapped[ImportJob] = relationship(back_populates="row_errors")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ImportRowError id={self.id} row={self.row_number}>"
