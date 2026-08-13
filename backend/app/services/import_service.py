"""Import service: CSV import job lifecycle + per-row error recording."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.models.enums import ImportStatus
from app.models.import_job import ImportJob
from app.models.import_row_error import ImportRowError
from app.repositories.import_job import ImportJobRepository, ImportRowErrorRepository
from app.services.base import commit_with_retry, utcnow

_MAX_CSV_BYTES = 50 * 1024 * 1024  # keep in sync with the endpoint limit


def _upload_path(job_id: uuid.UUID) -> Path:
    """Return the on-disk path for a job's uploaded CSV."""
    return Path(settings.UPLOAD_DIR) / f"{job_id}.csv"


class ImportService:
    """Owns import rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._jobs = ImportJobRepository(session)
        self._errors = ImportRowErrorRepository(session)

    # -- reads ----------------------------------------------------------

    async def get(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob:
        return await self._jobs.get_or_404(organization_id, job_id)

    async def list_jobs(
        self,
        organization_id: uuid.UUID,
        *,
        status: ImportStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImportJob]:
        return await self._jobs.list(organization_id, status=status, limit=limit, offset=offset)

    async def list_errors(
        self, organization_id: uuid.UUID, job_id: uuid.UUID
    ) -> list[ImportRowError]:
        await self._jobs.get_or_404(organization_id, job_id)
        return await self._errors.list_for_job(organization_id, job_id)

    async def count_active(self, organization_id: uuid.UUID) -> int:
        return await self._jobs.count_active(organization_id)

    # -- writes (endpoint-facing) --------------------------------------

    async def create(
        self,
        organization_id: uuid.UUID,
        *,
        created_by_user_id: uuid.UUID,
        file_name: str,
        file_size_bytes: int,
        lead_source_id: uuid.UUID | None = None,
    ) -> ImportJob:
        if await self._jobs.count_active(organization_id) > 0:
            raise AppError(
                code="import.active_job_exists",
                message="An import is already in progress; wait for it to finish",
                status_code=409,
            )
        job = ImportJob(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            lead_source_id=lead_source_id,
            status=ImportStatus.PENDING,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
        )
        self._jobs.add(job)
        await commit_with_retry(self._session)
        return job

    async def persist_upload(self, job_id: uuid.UUID, content: bytes) -> None:
        """Write an uploaded CSV to disk for the background worker."""
        if len(content) > _MAX_CSV_BYTES:
            raise AppError(
                code="import.file_too_large",
                message="Uploaded CSV exceeds the size limit",
                status_code=413,
            )
        path = _upload_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def upload_path(job_id: uuid.UUID) -> Path:
        """Expose the on-disk path for a job's CSV (worker uses it)."""
        return _upload_path(job_id)

    async def cancel(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob:
        job = await self._jobs.get_or_404(organization_id, job_id)
        if job.status not in (ImportStatus.PENDING, ImportStatus.PROCESSING):
            raise AppError(
                code="import.not_cancellable",
                message="Only pending/processing imports can be cancelled",
                status_code=400,
            )
        job.status = ImportStatus.CANCELLED
        job.finished_at = utcnow()
        await commit_with_retry(self._session)
        return job

    # -- writes (worker-facing) ----------------------------------------

    async def mark_processing(
        self, organization_id: uuid.UUID, job_id: uuid.UUID, *, total_rows: int
    ) -> ImportJob:
        job = await self._jobs.get_or_404(organization_id, job_id)
        job.status = ImportStatus.PROCESSING
        job.total_rows = total_rows
        job.started_at = utcnow()
        await commit_with_retry(self._session)
        return job

    async def record_row_error(
        self,
        organization_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        row_number: int,
        error_code: str,
        error_message: str,
        raw_row: dict[str, Any] | None = None,
    ) -> None:
        entry = ImportRowError(
            import_job_id=job_id,
            organization_id=organization_id,
            row_number=row_number,
            error_code=error_code,
            error_message=error_message,
            raw_row=raw_row or {},
        )
        self._errors.add(entry)

    async def mark_progress(
        self,
        organization_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        processed_rows: int,
        failed_rows: int,
    ) -> ImportJob:
        """Advance the counters; auto-completes when all rows are handled."""
        job = await self._jobs.get_or_404(organization_id, job_id)
        job.processed_rows = processed_rows
        job.failed_rows = failed_rows
        if processed_rows + failed_rows >= job.total_rows:
            job.status = ImportStatus.COMPLETED
            job.finished_at = utcnow()
        await commit_with_retry(self._session)
        return job

    async def mark_failed(
        self, organization_id: uuid.UUID, job_id: uuid.UUID, *, reason: str
    ) -> ImportJob:
        job = await self._jobs.get_or_404(organization_id, job_id)
        job.status = ImportStatus.FAILED
        job.finished_at = utcnow()
        metadata = dict(job.metadata_ or {})
        metadata["failure_reason"] = reason
        job.metadata_ = metadata
        await commit_with_retry(self._session)
        return job
