"""M11-C integration: AI run lifecycle, trace_id, idempotency, org isolation.

Exercises AgentService.create_run for the ``ai_run`` trigger against a real
PostgreSQL database with all migrations applied. Skipped automatically when no
PostgreSQL server is reachable (local dev), and run in CI against the
``postgres`` service.
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

from _pg_helpers import dsn_for_database, ensure_compat_roles  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.enums import AgentRunStatus, AgentRunTrigger  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.agent_service import AgentService  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402

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
    ensure_compat_roles(ADMIN_URL)
    db_name = f"agencyos_m11_{uuid.uuid4().hex[:8]}"
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


async def _register_org(factory, email: str = "owner@example.com") -> tuple[str, str, str]:
    async with factory() as session:
        service = AuthService(session)
        result = await service.register(
            __import__("app.schemas.auth", fromlist=["RegisterRequest"]).RegisterRequest(
                email=email,
                password="S3cure!pass",
                full_name="Owner",
                organization_name="Acme",
                organization_slug=f"acme-{uuid.uuid4().hex[:8]}",
            )
        )
        return str(result.user.id), result.access_token, result.refresh_token


async def _org_id_for_user(db, user_id: str) -> uuid.UUID:
    async with db() as session:
        result = await session.execute(
            sa_select(User.organization_id).where(User.id == uuid.UUID(user_id))
        )
        return result.scalar_one()


async def test_ai_run_persists_trace_and_trigger(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)
    trace_id = uuid.uuid4()
    key = "m11-key-1"

    async with db() as session:
        service = AgentService(session)
        run = await service.create_run(
            org_id,
            agent_name="ai_brain",
            trigger=AgentRunTrigger.AI_RUN,
            input_={"goal": "research_lead", "actor_user_id": user_id},
            idempotency_key=key,
            trace_id=trace_id,
        )
        assert run.trigger is AgentRunTrigger.AI_RUN
        assert run.status is AgentRunStatus.QUEUED
        assert run.trace_id == trace_id
        assert run.idempotency_key == key
        run_id = run.id

    # Read back through the same org to confirm persistence.
    async with db() as session:
        fetched = await AgentService(session).get_run(org_id, run_id)
        assert fetched.trace_id == trace_id
        assert fetched.trigger is AgentRunTrigger.AI_RUN
        assert fetched.idempotency_key == key


async def test_ai_run_idempotency_key_deduplicates(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)
    key = "m11-key-dedup"

    async with db() as session:
        service = AgentService(session)
        first = await service.create_run(
            org_id,
            agent_name="ai_brain",
            trigger=AgentRunTrigger.AI_RUN,
            input_={"goal": "search_leads"},
            idempotency_key=key,
        )
        second = await service.create_run(
            org_id,
            agent_name="ai_brain",
            trigger=AgentRunTrigger.AI_RUN,
            input_={"goal": "search_leads"},
            idempotency_key=key,
        )
        # Idempotent: the same key returns the existing row, not a duplicate.
        assert second.id == first.id
        assert second.trace_id == first.trace_id


async def test_ai_run_isolated_by_organization(db) -> None:
    a_uid, _, _ = await _register_org(db, email="org-a@example.com")
    b_uid, _, _ = await _register_org(db, email="org-b@example.com")
    org_a = await _org_id_for_user(db, a_uid)
    org_b = await _org_id_for_user(db, b_uid)

    async with db() as session:
        run = await AgentService(session).create_run(
            org_a,
            agent_name="ai_brain",
            trigger=AgentRunTrigger.AI_RUN,
            input_={"goal": "research_lead"},
            idempotency_key="m11-key-iso",
        )
        run_id = run.id

    # Org B must not be able to read Org A's AI run (tenant isolation).
    from app.core.errors import AppError

    async with db() as session:
        with pytest.raises(AppError) as exc_info:
            await AgentService(session).get_run(org_b, run_id)
        assert exc_info.value.status_code == 404
