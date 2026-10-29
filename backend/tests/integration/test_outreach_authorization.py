"""H2 integration: outreach write authorization against real PostgreSQL.

Companion to ``tests/api/test_outreach_rbac.py``. The API module proves the
permission dependency rejects VIEWER before the handler runs; this module proves
the same through the real application stack *and* a real database: rejected
writes leave zero rows behind, existing rows are not mutated, authorized roles
persist rows in their own tenant, and cross-tenant writes stay impossible.

Runs only where PostgreSQL is reachable (CI provides the ``postgres`` service);
skipped locally with the same reason as the other integration suites.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest

pytest.importorskip("psycopg2")
import httpx  # noqa: E402
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402
from sqlalchemy import func as sa_func  # noqa: E402
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
from app.api.deps import get_current_user, get_db  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import OutreachStatus, UserRole  # noqa: E402
from app.models.follow_up import FollowUp  # noqa: E402
from app.models.manual_outreach_queue import ManualOutreachQueue  # noqa: E402
from app.models.outreach_attempt import OutreachAttempt  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.auth import RegisterRequest  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.lead_service import LeadService  # noqa: E402
from app.services.outreach_service import OutreachService  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations"
ADMIN_URL = os.getenv(
    "TEST_POSTGRES_URL",
    settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres",
)
PREFIX = "/api/v1/outreach"
WRITE_ROLES = [
    UserRole.OWNER,
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.MEMBER,
    UserRole.SALES_AGENT,
]
TABLES = (OutreachAttempt, FollowUp, ManualOutreachQueue)


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
    db_name = f"agencyos_h2_{uuid.uuid4().hex[:8]}"
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


class _CookieCapture:
    def __init__(self) -> None:
        self.refresh_token: str | None = None

    def set_cookie(self, *, key: str, value: str, **kwargs: Any) -> None:
        if key == settings.REFRESH_COOKIE_NAME:
            self.refresh_token = value


async def _register_org(factory, email: str = "owner@example.com") -> tuple[str, str, str]:
    """Register an org via AuthService; returns (user_id, access, refresh)."""
    async with factory() as session:
        capture = _CookieCapture()
        result = await AuthService(session).register(
            RegisterRequest(
                email=email,
                password="S3cure!pass",
                full_name="Owner",
                organization_name="Acme",
                organization_slug=f"acme-{uuid.uuid4().hex[:8]}",
            ),
            response=capture,
        )
        assert capture.refresh_token is not None
        return str(result.user.id), result.access_token, capture.refresh_token


async def _org_id_for_user(factory, user_id: str) -> uuid.UUID:
    async with factory() as session:
        result = await session.execute(
            sa_select(User.organization_id).where(User.id == uuid.UUID(user_id))
        )
        return result.scalar_one()


@asynccontextmanager
async def _client_as(
    factory: Any, role: UserRole, organization_id: uuid.UUID, user_id: uuid.UUID
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Yield an HTTP client whose requests run in ``organization_id`` as ``role``."""

    async def _override_get_db() -> AsyncGenerator[Any, None]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=user_id, organization_id=organization_id, role=role
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _count(factory: Any, model: Any, organization_id: uuid.UUID) -> int:
    async with factory() as session:
        result = await session.execute(
            sa_select(sa_func.count())
            .select_from(model)
            .where(model.organization_id == organization_id)
        )
        return int(result.scalar_one())


async def _all_counts(factory: Any, organization_id: uuid.UUID) -> dict[str, int]:
    return {model.__name__: await _count(factory, model, organization_id) for model in TABLES}


async def _seed_lead(factory: Any, organization_id: uuid.UUID) -> uuid.UUID:
    async with factory() as session:
        lead = await LeadService(session).create(
            organization_id,
            {"email": f"lead-{uuid.uuid4().hex[:8]}@example.com", "first_name": "Ada"},
        )
        return lead.id


async def _seed_attempt(
    factory: Any, organization_id: uuid.UUID, lead_id: uuid.UUID
) -> uuid.UUID:
    async with factory() as session:
        attempt = await OutreachService(session).create_attempt(
            organization_id, {"lead_id": lead_id, "channel": "email"}
        )
        return attempt.id


async def _seed_follow_up(
    factory: Any, organization_id: uuid.UUID, lead_id: uuid.UUID
) -> uuid.UUID:
    async with factory() as session:
        follow_up = await OutreachService(session).create_follow_up(
            organization_id,
            {
                "lead_id": lead_id,
                "channel": "email",
                "sequence_position": 1,
                "body": "Checking in",
            },
        )
        return follow_up.id


async def _seed_manual_task(
    factory: Any, organization_id: uuid.UUID, lead_id: uuid.UUID
) -> uuid.UUID:
    async with factory() as session:
        task = await OutreachService(session).create_manual_task(
            organization_id, {"lead_id": lead_id, "channel": "email"}
        )
        return task.id


def _write_requests(
    lead_id: uuid.UUID, attempt_id: uuid.UUID, follow_up_id: uuid.UUID, task_id: uuid.UUID
) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (
            "POST",
            f"{PREFIX}/attempts",
            {"organization_id": str(uuid.uuid4()), "lead_id": str(lead_id), "channel": "email"},
        ),
        ("PATCH", f"{PREFIX}/attempts/{attempt_id}", {"status": "sent"}),
        (
            "POST",
            f"{PREFIX}/follow-ups",
            {
                "organization_id": str(uuid.uuid4()),
                "lead_id": str(lead_id),
                "channel": "email",
                "sequence_position": 1,
                "body": "Checking in",
            },
        ),
        ("PATCH", f"{PREFIX}/follow-ups/{follow_up_id}", {"status": "sent"}),
        (
            "POST",
            f"{PREFIX}/manual",
            {"organization_id": str(uuid.uuid4()), "lead_id": str(lead_id), "channel": "email"},
        ),
        ("PATCH", f"{PREFIX}/manual/{task_id}", {"status": "manually_sent"}),
    ]


# -- VIEWER is rejected with no side effects --------------------------------


async def test_viewer_writes_are_rejected_without_side_effects(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)
    lead_id = await _seed_lead(db, org_id)

    missing = uuid.uuid4()
    async with _client_as(db, UserRole.VIEWER, org_id, uuid.UUID(user_id)) as client:
        for method, path, payload in _write_requests(lead_id, missing, missing, missing):
            response = await client.request(method, path, json=payload)
            assert response.status_code == 403, (method, path, response.text)

    # The permission dependency runs before the handler: nothing was written.
    assert await _all_counts(db, org_id) == {
        "OutreachAttempt": 0,
        "FollowUp": 0,
        "ManualOutreachQueue": 0,
    }


async def test_viewer_cannot_mutate_existing_rows(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)
    lead_id = await _seed_lead(db, org_id)
    attempt_id = await _seed_attempt(db, org_id, lead_id)
    follow_up_id = await _seed_follow_up(db, org_id, lead_id)
    task_id = await _seed_manual_task(db, org_id, lead_id)

    async with _client_as(db, UserRole.VIEWER, org_id, uuid.UUID(user_id)) as client:
        for method, path, payload in [
            ("PATCH", f"{PREFIX}/attempts/{attempt_id}", {"status": "delivered"}),
            ("PATCH", f"{PREFIX}/follow-ups/{follow_up_id}", {"status": "delivered"}),
            ("PATCH", f"{PREFIX}/manual/{task_id}", {"status": "manually_sent"}),
        ]:
            response = await client.request(method, path, json=payload)
            assert response.status_code == 403, (method, path, response.text)

    async with db() as session:
        attempt = await session.get(OutreachAttempt, attempt_id)
        follow_up = await session.get(FollowUp, follow_up_id)
        task = await session.get(ManualOutreachQueue, task_id)
        assert attempt is not None and attempt.status is OutreachStatus.QUEUED
        assert follow_up is not None and follow_up.status is OutreachStatus.QUEUED
        assert task is not None and task.status is OutreachStatus.QUEUED


# -- authorized roles persist under their own tenant ----------------------


@pytest.mark.parametrize("role", WRITE_ROLES)
async def test_authorized_roles_can_write_outreach_records(db, role: UserRole) -> None:
    email = f"{role.value}-{uuid.uuid4().hex[:8]}@example.com"
    user_id, _, _ = await _register_org(db, email=email)
    org_id = await _org_id_for_user(db, user_id)
    lead_id = await _seed_lead(db, org_id)

    async with _client_as(db, role, org_id, uuid.UUID(user_id)) as client:
        attempt = await client.post(
            f"{PREFIX}/attempts",
            json={"organization_id": str(org_id), "lead_id": str(lead_id), "channel": "email"},
        )
        assert attempt.status_code == 201, attempt.text
        attempt_id = attempt.json()["id"]

        updated = await client.patch(f"{PREFIX}/attempts/{attempt_id}", json={"status": "sent"})
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "sent"

        follow_up = await client.post(
            f"{PREFIX}/follow-ups",
            json={
                "organization_id": str(org_id),
                "lead_id": str(lead_id),
                "channel": "email",
                "sequence_position": 1,
                "body": "Checking in",
            },
        )
        assert follow_up.status_code == 201, follow_up.text
        follow_up_id = follow_up.json()["id"]

        updated_follow_up = await client.patch(
            f"{PREFIX}/follow-ups/{follow_up_id}", json={"status": "sent"}
        )
        assert updated_follow_up.status_code == 200, updated_follow_up.text

        task = await client.post(
            f"{PREFIX}/manual",
            json={"organization_id": str(org_id), "lead_id": str(lead_id), "channel": "email"},
        )
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]

        updated_task = await client.patch(
            f"{PREFIX}/manual/{task_id}", json={"status": "manually_sent"}
        )
        assert updated_task.status_code == 200, updated_task.text

    assert await _all_counts(db, org_id) == {
        "OutreachAttempt": 1,
        "FollowUp": 1,
        "ManualOutreachQueue": 1,
    }


async def test_viewer_keeps_read_access(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)
    lead_id = await _seed_lead(db, org_id)
    await _seed_attempt(db, org_id, lead_id)
    await _seed_follow_up(db, org_id, lead_id)
    task_id = await _seed_manual_task(db, org_id, lead_id)

    async with _client_as(db, UserRole.VIEWER, org_id, uuid.UUID(user_id)) as client:
        attempts = await client.get(f"{PREFIX}/leads/{lead_id}/attempts")
        assert attempts.status_code == 200, attempts.text
        assert len(attempts.json()) == 1

        follow_ups = await client.get(f"{PREFIX}/leads/{lead_id}/follow-ups")
        assert follow_ups.status_code == 200, follow_ups.text
        assert len(follow_ups.json()) == 1

        manual = await client.get(f"{PREFIX}/manual")
        assert manual.status_code == 200, manual.text
        assert len(manual.json()) == 1

        single = await client.get(f"{PREFIX}/manual/{task_id}")
        assert single.status_code == 200, single.text

        messages = await client.get(f"{PREFIX}/messages")
        assert messages.status_code == 200, messages.text


# -- tenant isolation ------------------------------------------------------


@pytest.mark.parametrize(
    ("seed", "path_template"),
    [
        (_seed_attempt, f"{PREFIX}/attempts/{{id}}"),
        (_seed_follow_up, f"{PREFIX}/follow-ups/{{id}}"),
        (_seed_manual_task, f"{PREFIX}/manual/{{id}}"),
    ],
)
async def test_cross_tenant_updates_are_not_possible(db, seed, path_template: str) -> None:
    victim_user, _, _ = await _register_org(
        db, email=f"victim-{uuid.uuid4().hex[:8]}@example.com"
    )
    victim_org = await _org_id_for_user(db, victim_user)
    victim_lead = await _seed_lead(db, victim_org)
    victim_row = await seed(db, victim_org, victim_lead)

    attacker_user, _, _ = await _register_org(
        db, email=f"attacker-{uuid.uuid4().hex[:8]}@example.com"
    )
    attacker_org = await _org_id_for_user(db, attacker_user)

    async with _client_as(db, UserRole.OWNER, attacker_org, uuid.UUID(attacker_user)) as client:
        response = await client.patch(
            path_template.format(id=victim_row), json={"status": "delivered"}
        )
    assert response.status_code == 404, response.text

    async with db() as session:
        for model in TABLES:
            row = await session.get(model, victim_row)
            if row is not None:
                assert row.status is OutreachStatus.QUEUED


# -- unchanged admin-only surfaces ----------------------------------------


async def test_admin_only_writes_stay_admin_only(db) -> None:
    user_id, _, _ = await _register_org(db)
    org_id = await _org_id_for_user(db, user_id)

    async with _client_as(db, UserRole.MANAGER, org_id, uuid.UUID(user_id)) as client:
        message = await client.post(
            f"{PREFIX}/messages", json={"name": "n", "channel": "email", "body": "b"}
        )
        assert message.status_code == 403, message.text

        lead_source = await client.post("/api/v1/lead-sources", json={"name": "Referral"})
        assert lead_source.status_code == 403, lead_source.text
