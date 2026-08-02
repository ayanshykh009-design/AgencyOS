"""Integration tests: service layer against a real PostgreSQL database.

These cover the Phase 2 flows the unit suite cannot: real transactions,
generated dedup columns, refresh-token rotation, and the CSV import worker
(with savepoints). They are skipped automatically when no PostgreSQL server
is reachable (local dev), and run in CI against the ``postgres`` service.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

pytest.importorskip("psycopg2")
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402
from sqlalchemy import select as sa_select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.models.activity_log import ActivityLog  # noqa: E402
from app.models.enums import ImportStatus, LeadStatus  # noqa: E402
from app.models.import_job import ImportJob  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.auth import LoginRequest, RegisterRequest  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.import_service import ImportService  # noqa: E402
from app.services.lead_service import LeadService  # noqa: E402
from app.workers.import_worker import ImportWorker  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations"
ADMIN_URL = os.getenv(
    "TEST_POSTGRES_URL",
    settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres",
)


def _database_available() -> bool:
    try:
        conn = psycopg2.connect(ADMIN_URL, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(), reason="PostgreSQL server not reachable"
)


def _migration_files() -> list[Path]:
    return sorted(
        Path(MIGRATIONS_DIR).glob("[0-9][0-9][0-9][0-9]_*.sql"),
        key=lambda p: p.name,
    )


def _async_url_for(db_name: str) -> str:
    base = os.getenv("TEST_POSTGRES_URL", "").replace("+asyncpg", "") or settings.DATABASE_URL
    parts = urlsplit(base.replace("+asyncpg", ""))
    return urlunsplit(("postgresql+asyncpg", parts.netloc, f"/{db_name}", "", ""))


@pytest.fixture()
async def db():
    """Create a disposable database with all migrations applied, yield an
    async session factory, then drop it."""
    admin = psycopg2.connect(ADMIN_URL)
    admin.autocommit = True
    db_name = f"agencyos_svc_{uuid.uuid4().hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    conn = None
    engine = None
    try:
        params = admin.get_dsn_parameters()
        params["dbname"] = db_name
        conn = psycopg2.connect(**params)
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE public.schema_migrations ("
                " version text PRIMARY KEY,"
                " applied_at timestamptz NOT NULL DEFAULT now())"
            )
        conn.commit()
        for migration in _migration_files():
            with conn.cursor() as cur:
                cur.execute(migration.read_text(encoding="utf-8"))
            conn.commit()

        engine = create_async_engine(_async_url_for(db_name), poolclass=NullPool)
        factory = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )
        yield factory
    finally:
        if engine is not None:
            await engine.dispose()
        if conn is not None:
            conn.close()
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db_name)))
        admin.close()


async def _register_org(factory, email: str = "owner@example.com") -> tuple[str, str, str]:
    """Register an org via AuthService; returns (user_id, access, refresh)."""
    async with factory() as session:
        service = AuthService(session)
        result = await service.register(
            RegisterRequest(
                email=email,
                password="S3cure!pass",
                full_name="Owner",
                organization_name="Acme",
                organization_slug=f"acme-{uuid.uuid4().hex[:8]}",
            )
        )
        return str(result.user.id), result.access_token, result.refresh_token


async def test_register_login_refresh_roundtrip(db) -> None:
    user_id, access, refresh = await _register_org(db)

    assert access and refresh
    assert user_id

    async with db() as session:
        service = AuthService(session)
        result = await service.login(
            LoginRequest(email="owner@example.com", password="S3cure!pass")
        )
        assert result.user.id and str(result.user.id) == user_id

        # Refresh rotates: the old token must stop working afterwards.
        rotated = await service.refresh(refresh)
        assert rotated.access_token != access
        with pytest.raises(AppError) as exc_info:
            await service.refresh(refresh)
        assert exc_info.value.status_code == 401


async def test_login_wrong_password_rejected(db) -> None:
    await _register_org(db)
    async with db() as session:
        service = AuthService(session)
        with pytest.raises(AppError) as exc_info:
            await service.login(
                LoginRequest(email="owner@example.com", password="wrong-pass")
            )
        assert exc_info.value.status_code == 401


async def test_duplicate_email_registration_rejected(db) -> None:
    user_id, _, _ = await _register_org(db)
    async with db() as session:
        service = AuthService(session)
        with pytest.raises(AppError) as exc_info:
            await service.register(
                RegisterRequest(
                    email="owner@example.com",
                    password="S3cure!pass",
                    full_name="Other",
                    organization_name="Other",
                    organization_slug=f"other-{uuid.uuid4().hex[:8]}",
                )
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "user.email_taken"


async def test_lead_lifecycle_and_status_activity(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    async with db() as session:
        service = LeadService(session)
        lead = await service.create(
            org_id,
            {"email": "ada@example.com", "first_name": "Ada", "last_name": "Lovelace"},
        )
        assert lead.status is LeadStatus.NEW
        assert lead.email_normalized == "ada@example.com"

        # Duplicate normalized email -> 409.
        with pytest.raises(AppError) as exc_info:
            await service.create(org_id, {"email": "ADA@example.com"})
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "lead.duplicate"

        # Funnel reflects the created lead.
        funnel = await service.funnel(org_id)
        assert funnel.get(LeadStatus.NEW) == 1

        # Marking won writes an activity log row.
        await service.update(org_id, lead.id, {"status": LeadStatus.WON})
        updated = await service.get(org_id, lead.id)
        assert updated.status is LeadStatus.WON

        result = await session.execute(
            sa_select(ActivityLog).where(
                ActivityLog.organization_id == org_id,
                ActivityLog.lead_id == lead.id,
            )
        )
        events = result.scalars().all()
        assert any(e.event_type.value == "lead_won" for e in events)


async def test_import_worker_parses_and_inserts_leads(db, monkeypatch) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    async with db() as session:
        imports = ImportService(session)
        job = await imports.create(
            org_id,
            created_by_user_id=uuid.UUID(user_id),
            file_name="leads.csv",
            file_size_bytes=120,
        )
        job_id = job.id
    await imports.persist_upload(job_id, b"email,first_name\nbob@example.com,Bob\n")

    monkeypatch.setattr("app.workers.import_worker.async_session_factory", db)

    await ImportWorker.process_job(job_id, org_id)

    async with db() as session:
        result = await session.execute(sa_select(ImportJob).where(ImportJob.id == job_id))
        stored = result.scalar_one()
        assert stored.status is ImportStatus.COMPLETED
        assert stored.processed_rows == 1
        assert stored.failed_rows == 0

        leads = LeadService(session)
        matches, total = await leads.search(org_id, query="bob")
        assert total == 1
        assert matches[0].email == "bob@example.com"


async def test_import_worker_rejects_invalid_rows(db, monkeypatch) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    async with db() as session:
        imports = ImportService(session)
        job = await imports.create(
            org_id,
            created_by_user_id=uuid.UUID(user_id),
            file_name="bad.csv",
            file_size_bytes=60,
        )
        job_id = job.id
    await imports.persist_upload(
        job_id, b"email\nnot-an-email\n"  # one invalid row, no contact key
    )

    monkeypatch.setattr("app.workers.import_worker.async_session_factory", db)

    await ImportWorker.process_job(job_id, org_id)

    async with db() as session:
        result = await session.execute(sa_select(ImportJob).where(ImportJob.id == job_id))
        stored = result.scalar_one()
        assert stored.status is ImportStatus.COMPLETED
        assert stored.processed_rows == 0
        assert stored.failed_rows == 1

        errors = await ImportService(session).list_errors(org_id, job_id)
        assert len(errors) == 1
        assert errors[0].error_code == "import.invalid_row"


async def _org_id_for_user(db, user_id: str) -> uuid.UUID:
    async with db() as session:
        result = await session.execute(
            sa_select(User.organization_id).where(User.id == uuid.UUID(user_id))
        )
        return result.scalar_one()
