"""CSV import worker: parses uploads, validates rows, inserts leads.

Runs in the request's background task (or a queue once added). It owns its own
session and transaction: rows are inserted with savepoints so a single bad row
never aborts the import. Duplicates and validation failures are recorded as
``import_row_errors`` and surfaced through the API.

The worker uses repositories directly (not the ImportService, whose methods
commit mid-flight); progress is flushed in chunks inside one outer transaction.
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, ImportStatus, LeadStatus
from app.models.import_job import ImportJob
from app.models.import_row_error import ImportRowError
from app.models.lead import Lead
from app.repositories.import_job import ImportJobRepository
from app.repositories.lead import LeadRepository
from app.services.base import utcnow
from app.services.import_service import ImportService

logger = logging.getLogger("agencyos")

# Human-friendly header aliases -> canonical field names.
_HEADER_ALIASES: dict[str, str] = {
    "first_name": "first_name",
    "firstname": "first_name",
    "first name": "first_name",
    "last_name": "last_name",
    "lastname": "last_name",
    "last name": "last_name",
    "email": "email",
    "phone": "phone",
    "whatsapp": "whatsapp",
    "website": "website",
    "company": "company",
    "position": "position",
    "title": "position",
    "location": "location",
    "linkedin": "linkedin_url",
    "linkedin_url": "linkedin_url",
    "notes": "notes",
}

_CONTACT_FIELDS = ("email", "phone", "whatsapp", "website")
_STRING_FIELDS = (
    "first_name", "last_name", "company", "position", "location",
    "linkedin_url", "notes",
)


class ImportWorker:
    """Process one import job end-to-end."""

    @classmethod
    async def process_job(
        cls,
        job_id: uuid.UUID,
        organization_id: uuid.UUID,
        lead_source_id: uuid.UUID | None = None,
    ) -> None:
        """Run the import; safe to call from a background task."""
        try:
            await cls._run(job_id, organization_id, lead_source_id)
        except Exception:
            logger.exception("import job %s failed", job_id)
            await cls._mark_failed(job_id, organization_id)

    @classmethod
    async def _run(
        cls,
        job_id: uuid.UUID,
        organization_id: uuid.UUID,
        lead_source_id: uuid.UUID | None,
    ) -> None:
        content = ImportService.upload_path(job_id).read_bytes()
        rows = _parse_csv(content)

        async with async_session_factory() as session:
            jobs = ImportJobRepository(session)
            leads = LeadRepository(session)
            job = await jobs.get_or_404(organization_id, job_id)
            if job.status is not ImportStatus.PENDING:
                return

            job.status = ImportStatus.PROCESSING
            job.total_rows = len(rows)
            job.started_at = utcnow()
            await session.flush()

            processed = 0
            failed = 0
            for index, raw in enumerate(rows, start=2):  # +1 for the header
                parsed, error = _parse_row(raw)
                if error:
                    session.add(
                        _row_error(
                            job_id, organization_id, index,
                            "import.invalid_row", error, raw,
                        )
                    )
                    failed += 1
                    job.failed_rows = failed
                    continue

                duplicate = await leads.find_duplicates(
                    organization_id,
                    email_normalized=(parsed.get("email") or "").lower() or None,
                    phone_normalized=_digits(parsed.get("phone")),
                    website_domain=_domain(parsed.get("website")),
                )
                if duplicate:
                    session.add(
                        _row_error(
                            job_id, organization_id, index,
                            "import.duplicate", "Lead already exists", raw,
                        )
                    )
                    failed += 1
                    job.failed_rows = failed
                    continue

                await _insert_with_savepoint(
                    session, leads, job, organization_id,
                    lead_source_id, parsed, index, raw,
                )
                processed += 1
                job.processed_rows = processed

                if (processed + failed) % settings.IMPORT_CHUNK_SIZE == 0:
                    await session.flush()

            job.status = ImportStatus.COMPLETED
            job.finished_at = utcnow()
            session.add(
                ActivityLog(
                    organization_id=organization_id,
                    user_id=job.created_by_user_id,
                    event_type=ActivityEventType.LEAD_IMPORTED,
                    entity_type="import_job",
                    entity_id=job.id,
                    description=(
                        f"Imported {processed} lead(s) from {job.file_name} "
                        f"({failed} row(s) rejected)"
                    ),
                    metadata={"processed": processed, "failed": failed},
                    occurred_at=utcnow(),
                )
            )
            await session.commit()

            logger.info(
                "import job %s completed: %d processed, %d failed",
                job_id, processed, failed,
            )

    @classmethod
    async def _mark_failed(
        cls, job_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """Best-effort: flag the job failed after an unexpected error."""
        try:
            async with async_session_factory() as session:
                job = await ImportJobRepository(session).get_or_404(
                    organization_id, job_id
                )
                job.status = ImportStatus.FAILED
                job.finished_at = utcnow()
                await session.commit()
        except Exception:
            logger.exception("could not mark import job %s failed", job_id)


def _parse_csv(content: bytes) -> list[dict[str, str]]:
    """Parse CSV bytes into a list of header-keyed dicts (header normalized)."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, str]] = []
    for raw in reader:
        row: dict[str, str] = {}
        for header, value in raw.items():
            key = _HEADER_ALIASES.get((header or "").strip().lower(), header or "")
            row[key] = (value or "").strip()
        rows.append(row)
    return rows


def _parse_row(raw: dict[str, str]) -> tuple[dict[str, Any], str | None]:
    """Validate + normalize a single CSV row."""
    parsed: dict[str, Any] = {}
    for field in _STRING_FIELDS:
        value = raw.get(field)
        if value:
            parsed[field] = value
    email = (raw.get("email") or "").strip().lower()
    if email:
        if "@" not in email or "." not in email.split("@")[-1]:
            return {}, "email must be valid"
        parsed["email"] = email
    for field in ("phone", "whatsapp"):
        digits = _digits(raw.get(field))
        if digits:
            parsed[field] = digits
    website = (raw.get("website") or "").strip()
    if website:
        parsed["website"] = website
    if not any(parsed.get(f) for f in _CONTACT_FIELDS):
        return {}, "at least one of email/phone/whatsapp/website is required"
    return parsed, None


async def _insert_with_savepoint(
    session,
    leads: LeadRepository,
    job: ImportJob,
    organization_id: uuid.UUID,
    lead_source_id: uuid.UUID | None,
    parsed: dict[str, Any],
    index: int,
    raw: dict[str, str],
) -> bool:
    """Insert one lead atomically; records a duplicate error on collision."""
    def build() -> Lead:
        return Lead(
            organization_id=organization_id,
            lead_source_id=lead_source_id,
            status=LeadStatus.NEW,
            first_name=parsed.get("first_name"),
            last_name=parsed.get("last_name"),
            company=parsed.get("company"),
            position=parsed.get("position"),
            location=parsed.get("location"),
            linkedin_url=parsed.get("linkedin_url"),
            email=parsed.get("email"),
            phone=parsed.get("phone"),
            whatsapp=parsed.get("whatsapp"),
            website=parsed.get("website"),
            notes=parsed.get("notes"),
        )

    session.add(build())
    try:
        async with session.begin_nested():
            await session.flush()
        return True
    except IntegrityError:
        # The savepoint rolled back (only this row's insert was discarded).
        session.add(
            _row_error(
                job.id, organization_id, index,
                "import.duplicate", "Lead already exists (race condition)", raw,
            )
        )
        return False


def _row_error(
    job_id: uuid.UUID,
    organization_id: uuid.UUID,
    row_number: int,
    error_code: str,
    error_message: str,
    raw_row: dict[str, str],
) -> ImportRowError:
    return ImportRowError(
        import_job_id=job_id,
        organization_id=organization_id,
        row_number=row_number,
        error_code=error_code,
        error_message=error_message,
        raw_row=raw_row,
    )


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits or None


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    from app.schemas.lead import _normalize_domain

    return _normalize_domain(url)
