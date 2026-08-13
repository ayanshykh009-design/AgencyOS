"""Import endpoints: CSV upload, job status, errors, cancellation.

The CSV file is stored under ``UPLOAD_DIR`` and processed by the background
import worker (app/workers/import_worker.py). Jobs are org-scoped and only one
active import per organization is allowed at a time.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile

from app.api.deps import CurrentUser, DbSession, require_role
from app.core.config import settings
from app.core.errors import AppError
from app.models.enums import ImportStatus, UserRole
from app.schemas.imports import ImportJobRead, ImportRowErrorRead
from app.services.import_service import ImportService
from app.workers.import_worker import ImportWorker

router = APIRouter()

_admin_only = require_role(UserRole.OWNER, UserRole.ADMIN)

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post(
    "",
    response_model=ImportJobRead,
    status_code=201,
    summary="Upload a CSV to import as leads",
    dependencies=[Depends(_admin_only)],
)
async def create_import(
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    lead_source_id: uuid.UUID | None = Form(default=None),
) -> ImportJobRead:
    """Accept a CSV upload, create a job, and enqueue background processing."""
    service = ImportService(db)
    file_name = file.filename or "leads.csv"
    if not file_name.lower().endswith(".csv"):
        raise AppError(
            code="import.not_csv",
            message="Only .csv files can be imported",
            status_code=400,
        )
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise AppError(
            code="import.file_too_large",
            message=f"CSV must be at most {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
            status_code=413,
        )
    if len(content) == 0:
        raise AppError(
            code="import.empty_file",
            message="The uploaded file is empty",
            status_code=400,
        )

    job = await service.create(
        current_user.organization_id,
        created_by_user_id=current_user.id,
        file_name=file_name,
        file_size_bytes=len(content),
        lead_source_id=lead_source_id,
    )
    await service.persist_upload(job.id, content)
    if settings.IMPORT_WORKER_ENABLED:
        background_tasks.add_task(
            ImportWorker.process_job,
            job.id,
            current_user.organization_id,
            lead_source_id,
        )
    return ImportJobRead.model_validate(job)


@router.get(
    "",
    response_model=list[ImportJobRead],
    summary="List import jobs",
)
async def list_imports(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: ImportStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ImportJobRead]:
    service = ImportService(db)
    jobs = await service.list_jobs(
        current_user.organization_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [ImportJobRead.model_validate(j) for j in jobs]


@router.get(
    "/{job_id}",
    response_model=ImportJobRead,
    summary="Get an import job",
)
async def get_import(job_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ImportJobRead:
    service = ImportService(db)
    job = await service.get(current_user.organization_id, job_id)
    return ImportJobRead.model_validate(job)


@router.get(
    "/{job_id}/errors",
    response_model=list[ImportRowErrorRead],
    summary="List rejected rows for an import job",
)
async def get_import_errors(
    job_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> list[ImportRowErrorRead]:
    service = ImportService(db)
    errors = await service.list_errors(current_user.organization_id, job_id)
    return [ImportRowErrorRead.model_validate(e) for e in errors]


@router.post(
    "/{job_id}/cancel",
    response_model=ImportJobRead,
    summary="Cancel a pending/processing import",
    dependencies=[Depends(_admin_only)],
)
async def cancel_import(
    job_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ImportJobRead:
    service = ImportService(db)
    job = await service.cancel(current_user.organization_id, job_id)
    return ImportJobRead.model_validate(job)
