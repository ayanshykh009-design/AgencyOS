"""ImportJob model — a CSV import run (import-only; Postgres is source of truth)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ImportStatus

if TYPE_CHECKING:
    from app.models.import_row_error import ImportRowError
    from app.models.lead_source import LeadSource
    from app.models.user import User


class ImportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks the state of one CSV import."""

    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint("length(btrim(file_name)) > 0", name="chk_import_jobs_file_name"),
        CheckConstraint("file_size_bytes >= 0", name="chk_import_jobs_file_size"),
        CheckConstraint("total_rows >= 0", name="chk_import_jobs_total_rows"),
        CheckConstraint("processed_rows >= 0", name="chk_import_jobs_processed_rows"),
        CheckConstraint("failed_rows >= 0", name="chk_import_jobs_failed_rows"),
        CheckConstraint(
            "processed_rows <= total_rows AND failed_rows <= total_rows",
            name="chk_import_jobs_counts",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    lead_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead_sources.id", ondelete="SET NULL")
    )
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, name="import_status", native_enum=True, validate_strings=True),
        default=ImportStatus.PENDING,
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    created_by: Mapped[User] = relationship()
    lead_source: Mapped[LeadSource | None] = relationship()
    row_errors: Mapped[list[ImportRowError]] = relationship(
        back_populates="import_job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ImportJob id={self.id} status={self.status}>"
