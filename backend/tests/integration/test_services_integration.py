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

from _pg_helpers import (  # noqa: E402
    dsn_for_database,
    ensure_compat_roles,
    enum_bootstrap_files,
)
from app.core.config import settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.models.activity_log import ActivityLog  # noqa: E402
from app.models.enums import (  # noqa: E402
    CredentialType,
    ExecutionStatus,
    ImportStatus,
    LeadStatus,
    WorkflowTriggerType,
)
from app.models.import_job import ImportJob  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.auth import LoginRequest, RegisterRequest  # noqa: E402
from app.schemas.credential import CredentialCreate  # noqa: E402
from app.schemas.workflow import WorkflowCreate  # noqa: E402
from app.schemas.workflow_execution import WorkflowExecutionCreate  # noqa: E402
from app.schemas.workflow_trigger import WorkflowTriggerCreate  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.base import utcnow  # noqa: E402
from app.services.credential_service import CredentialService  # noqa: E402
from app.services.import_service import ImportService  # noqa: E402
from app.services.lead_service import LeadService  # noqa: E402
from app.services.schedule_dispatcher import ScheduleDispatcher  # noqa: E402
from app.services.workflow_execution_service import WorkflowExecutionService  # noqa: E402
from app.services.workflow_service import WorkflowService  # noqa: E402
from app.services.workflow_trigger_service import WorkflowTriggerService  # noqa: E402
from app.workers.execution_worker import ExecutionWorker  # noqa: E402
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
    return enum_bootstrap_files() + sorted(
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
    ensure_compat_roles(ADMIN_URL)
    db_name = f"agencyos_svc_{uuid.uuid4().hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    conn = None
    engine = None
    try:
        conn = psycopg2.connect(dsn_for_database(ADMIN_URL, db_name))
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


async def test_db_fixture_preserves_password_auth(db) -> None:
    # Regression for BASELINE-DB-001: the `db` fixture's per-test database
    # connection must authenticate with the password from ADMIN_URL. A
    # successful query through the async engine proves the clone preserved auth
    # and migrations were applied to this disposable database.
    async with db() as session:
        result = await session.execute(sa_select(1))
        assert result.scalar_one() == 1


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


async def test_schedule_dispatcher_reserves_and_queues_once(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    async with db() as session:
        workflow = await WorkflowService(session).create(
            WorkflowCreate(
                organization_id=org_id,
                name="Daily sync",
                execution_mode="builtin",
            ),
            created_by_user_id=uuid.UUID(user_id),
        )
        await WorkflowService(session).activate(org_id, workflow.id)
        trigger = await WorkflowTriggerService(session).create(
            WorkflowTriggerCreate(
                organization_id=org_id,
                workflow_id=workflow.id,
                name="Morning run",
                trigger_type=WorkflowTriggerType.SCHEDULE,
                schedule_cron="*/5 * * * *",
                enabled=True,
            )
        )

    async with db() as session:
        stats = await ScheduleDispatcher(session).dispatch_due(now=utcnow())
        assert stats["queued"] == 1
        assert stats["failed"] == 0
        assert stats["conflicts"] == 0

    async with db() as session:
        executions = await WorkflowExecutionService(session).list_executions(org_id)
        assert len(executions) == 1
        assert executions[0].trigger_id == trigger.id
        assert executions[0].status is ExecutionStatus.QUEUED

        stored = await WorkflowTriggerService(session).get_trigger(org_id, trigger.id)
        assert stored.last_fired_at is not None

        # Same tick must never dispatch twice (idempotent across sweeps).
        stats = await ScheduleDispatcher(session).dispatch_due(now=utcnow())
        assert stats["queued"] == 0
        assert stats["skipped"] == 1
        executions = await WorkflowExecutionService(session).list_executions(org_id)
        assert len(executions) == 1


async def test_schedule_dispatcher_skips_inactive_workflow(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    async with db() as session:
        workflow = await WorkflowService(session).create(
            WorkflowCreate(
                organization_id=org_id,
                name="Draft only",
                execution_mode="builtin",
            ),
            created_by_user_id=uuid.UUID(user_id),
        )
        # Trigger on a DRAFT workflow: must be invisible to the dispatcher.
        await WorkflowTriggerService(session).create(
            WorkflowTriggerCreate(
                organization_id=org_id,
                workflow_id=workflow.id,
                name="Never fires",
                trigger_type=WorkflowTriggerType.SCHEDULE,
                schedule_cron="*/5 * * * *",
                enabled=True,
            )
        )

    async with db() as session:
        stats = await ScheduleDispatcher(session).dispatch_due(now=utcnow())
        assert stats["queued"] == 0
        assert stats["scanned"] == 0


async def test_credential_rotate_reencrypts_under_new_key(db, monkeypatch) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", "integration-old-key")
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "1")

    async with db() as session:
        service = CredentialService(session)
        credential = await service.create(
            CredentialCreate(
                organization_id=org_id,
                name="n8n key",
                credential_type=CredentialType.N8N_API_KEY,
                encrypted_value="integration-secret",
                value_preview="inte",
            ),
            created_by_user_id=uuid.UUID(user_id),
        )
        stored_id = credential.id
        assert credential.key_version == "1"
        assert credential.encrypted_value.startswith("v1:")
        assert await service.get_secret(org_id, credential.id) == "integration-secret"

    # Rotate the master key: the old key becomes the dual-read previous key.
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY", "integration-new-key")
    monkeypatch.setattr(settings, "CREDENTIALS_ENC_KEY_PREVIOUS", "integration-old-key")
    monkeypatch.setattr(settings, "CREDENTIAL_KEY_VERSION", "2")

    async with db() as session:
        service = CredentialService(session)
        # Still readable through the previous key before rekey.
        assert await service.get_secret(org_id, stored_id) == "integration-secret"
        rotated = await service.rotate(org_id, stored_id)
        assert rotated.key_version == "2"
        assert rotated.encrypted_value.startswith("v2:")
        assert rotated.last_rotated_at is not None
        # Now decrypts under the new current key.
        assert await service.get_secret(org_id, stored_id) == "integration-secret"


async def test_builtin_workflow_executes_in_process(db, monkeypatch) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    async with db() as session:
        workflow = await WorkflowService(session).create(
            WorkflowCreate(
                organization_id=org_id,
                name="Segment lead",
                execution_mode="builtin",
                definition={
                    "steps": [
                        {"type": "copy", "from": "input.lead", "to": "lead"},
                        {
                            "type": "condition",
                            "if": {"path": "lead.score", "op": "gte", "value": 50},
                            "then": [
                                {"type": "set", "key": "segment", "value": "hot"}
                            ],
                            "else": [
                                {"type": "set", "key": "segment", "value": "cold"}
                            ],
                        },
                    ],
                    "output_key": "segment",
                },
            ),
            created_by_user_id=uuid.UUID(user_id),
        )
        await WorkflowService(session).activate(org_id, workflow.id)
        workflow_id = workflow.id

        execution = await WorkflowExecutionService(session).queue(
            WorkflowExecutionCreate(
                organization_id=org_id,
                workflow_id=workflow_id,
                input={"lead": {"score": 70}},
            )
        )
        execution_id = execution.id

    # Run the worker's queue phase against the real DB.
    monkeypatch.setattr("app.workers.execution_worker.async_session_factory", db)
    processed = await ExecutionWorker.process_queued(batch_size=10)
    assert processed == 1

    async with db() as session:
        stored = await WorkflowExecutionService(session).get_execution(org_id, execution_id)
        assert stored.status is ExecutionStatus.SUCCEEDED
        assert stored.output == {"segment": "hot"}


async def test_builtin_workflow_failure_retries_like_other_adapters(db, monkeypatch) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    async with db() as session:
        workflow = await WorkflowService(session).create(
            WorkflowCreate(
                organization_id=org_id,
                name="Broken builtin",
                execution_mode="builtin",
                definition={
                    "steps": [
                        {"type": "error_if", "message": "no email",
                         "if": {"path": "input.lead.email", "op": "missing"}}
                    ]
                },
            ),
            created_by_user_id=uuid.UUID(user_id),
        )
        await WorkflowService(session).activate(org_id, workflow.id)
        execution = await WorkflowExecutionService(session).queue(
            WorkflowExecutionCreate(
                organization_id=org_id,
                workflow_id=workflow.id,
                input={"lead": {"score": 70}},
                max_attempts=1,
            )
        )
        execution_id = execution.id

    monkeypatch.setattr("app.workers.execution_worker.async_session_factory", db)
    await ExecutionWorker.process_queued(batch_size=10)

    async with db() as session:
        stored = await WorkflowExecutionService(session).get_execution(org_id, execution_id)
        assert stored.status is ExecutionStatus.FAILED
        assert stored.error == {
            "error": "adapter_error",
            "message": "no email",
        }


async def _org_id_for_user(db, user_id: str) -> uuid.UUID:
    async with db() as session:
        result = await session.execute(
            sa_select(User.organization_id).where(User.id == uuid.UUID(user_id))
        )
        return result.scalar_one()
