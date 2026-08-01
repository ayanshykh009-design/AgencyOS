"""ImportJob repository: jobs and per-row errors."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import ImportStatus
from app.models.import_job import ImportJob
from app.models.import_row_error import ImportRowError


class ImportJobRepository:
    """Data access for CSV import jobs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob | None:
        job = await self._session.get(ImportJob, job_id)
        if job is None or job.organization_id != organization_id:
            return None
        return job

    async def get_or_404(
        self, organization_id: uuid.UUID, job_id: uuid.UUID
    ) -> ImportJob:
        job = await self.get(organization_id, job_id)
        if job is None:
            raise AppError(
                code="import_job.not_found",
                message="Import job not found",
                status_code=404,
            )
        return job

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        status: ImportStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImportJob]:
        stmt = select(ImportJob).where(
            ImportJob.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(ImportJob.status == status)
        stmt = stmt.order_by(ImportJob.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self, organization_id: uuid.UUID) -> int:
        """Count pending/processing jobs (dashboard + concurrency guard)."""
        stmt = (
            select(func.count(ImportJob.id))
            .where(
                ImportJob.organization_id == organization_id,
                ImportJob.status.in_([ImportStatus.PENDING, ImportStatus.PROCESSING]),
            )
            .select_from(ImportJob)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def add(self, job: ImportJob) -> None:
        self._session.add(job)


class ImportRowErrorRepository:
    """Data access for rejected CSV rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_job(
        self, organization_id: uuid.UUID, job_id: uuid.UUID
    ) -> list[ImportRowError]:
        stmt = (
            select(ImportRowError)
            .where(
                ImportRowError.organization_id == organization_id,
                ImportRowError.import_job_id == job_id,
            )
            .order_by(ImportRowError.row_number)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, row_error: ImportRowError) -> None:
        self._session.add(row_error)
