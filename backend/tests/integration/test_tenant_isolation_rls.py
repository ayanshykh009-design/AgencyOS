"""Integration tests: PostgreSQL-enforced tenant isolation (B-3).

Behavioral proof for the backend RLS migration (0033): the ``agencyos_app``
role must see and mutate ONLY its own tenant, cross-tenant writes must fail
with SQLSTATE 42501, ``agencyos_worker`` bypasses RLS (BYPASSRLS), and the
SECURITY DEFINER auth lookups keep working before any identity exists.

These tests are skipped automatically when no PostgreSQL server is reachable
(local dev) and run in CI against the disposable ``postgres`` service. Static
contract checks (no DB) live in ``test_rls_policy_coverage.py``; the async
service-level flow is exercised here too because only a real database can
prove the WITH CHECK / USING predicates.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import event
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytest.importorskip("psycopg2")
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402

from _pg_helpers import (  # noqa: E402
    dsn_for_database,
    ensure_compat_roles,
    enum_bootstrap_files,
)
from app.api.deps import get_current_user  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import _restore_tenant_guc  # noqa: E402
from app.core.tenant_context import (  # noqa: E402
    activate_org,
    set_current_organization_id,
)
from app.schemas.auth import LoginRequest, RegisterRequest  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402

ADMIN_URL = os.getenv(
    "TEST_POSTGRES_URL",
    settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres",
)

GUC = "app.current_organization_id"

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations"

ORG_A = "00000000-0000-0000-0000-0000000000a1"
ORG_B = "00000000-0000-0000-0000-0000000000b2"
USER_A = "00000000-0000-0000-0000-0000000000a4"
USER_B = "00000000-0000-0000-0000-0000000000b4"
LEAD_A = "00000000-0000-0000-0000-0000000000a5"
LEAD_B = "00000000-0000-0000-0000-0000000000b5"
REFRESH_TOKEN_A = "seed-refresh-token-hash-a"
INVITE_TOKEN_A = "seed-invite-token-hash-a"


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


def _migration_files():
    return enum_bootstrap_files() + sorted(
        MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"),
        key=lambda p: p.name,
    )


def _async_url_for(db_name: str) -> str:
    base = os.getenv("TEST_POSTGRES_URL", "").replace("+asyncpg", "") or settings.DATABASE_URL
    parts = urlsplit(base.replace("+asyncpg", ""))
    return urlunsplit(("postgresql+asyncpg", parts.netloc, f"/{db_name}", "", ""))


def _seed(cur) -> None:
    cur.execute(
        f"""
        INSERT INTO public.organizations (id, name, slug) VALUES
          ('{ORG_A}', 'Org Alpha', 'org-alpha'),
          ('{ORG_B}', 'Org Beta',  'org-beta');

        INSERT INTO public.users (id, organization_id, email, full_name) VALUES
          ('{USER_A}', '{ORG_A}', 'usera@example.com', 'User A'),
          ('{USER_B}', '{ORG_B}', 'userb@example.com', 'User B');

        INSERT INTO public.leads (id, organization_id, first_name) VALUES
          ('{LEAD_A}', '{ORG_A}', 'Lead A'),
          ('{LEAD_B}', '{ORG_B}', 'Lead B');

        INSERT INTO public.refresh_tokens
          (id, user_id, organization_id, token_hash, expires_at)
        VALUES
          ('00000000-0000-0000-0000-0000000000a6', '{USER_A}', '{ORG_A}',
           '{REFRESH_TOKEN_A}', now() + interval '1 day');

        INSERT INTO public.team_invites
          (id, organization_id, email, token_hash, expires_at)
        VALUES
          ('00000000-0000-0000-0000-0000000000a7', '{ORG_A}',
           'invite-a@example.com', '{INVITE_TOKEN_A}', now() + interval '1 day');
        """
    )


@pytest.fixture(scope="module")
def seeded_db():
    """Disposable migrated database with two tenants seeded (module-scoped)."""
    admin = psycopg2.connect(ADMIN_URL)
    admin.autocommit = True
    ensure_compat_roles(ADMIN_URL)
    db_name = f"agencyos_rls_{uuid.uuid4().hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    conn = None
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
        # SET ROLE requires membership; idempotent, cluster-global, test-only.
        with conn.cursor() as cur:
            cur.execute("GRANT agencyos_app, agencyos_worker TO CURRENT_USER")
            _seed(cur)
        conn.commit()
        yield db_name
    finally:
        if conn is not None:
            conn.close()
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db_name))
            )
        admin.close()


def _connect(db_name: str, role: str | None = None):
    """Fresh session-level connection (optionally switched to an app role)."""
    conn = psycopg2.connect(dsn_for_database(ADMIN_URL, db_name))
    conn.autocommit = True
    if role:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
    return conn


def _scalar(conn, statement: str, params=()):
    with conn.cursor() as cur:
        cur.execute(statement, params)
        row = cur.fetchone()
    return row[0] if row else None


def _set_guc(conn, value: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT set_config('{GUC}', %s, false)", (value,))


def _owner_scalar(db_name: str, statement: str, params=()):
    conn = psycopg2.connect(dsn_for_database(ADMIN_URL, db_name))
    try:
        return _scalar(conn, statement, params)
    finally:
        conn.close()


# --- role / policy behavior (sync) ----------------------------------------


def test_0033_roles_exist_with_expected_attributes(seeded_db):
    conn = _connect(seeded_db)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rolname, rolcanlogin, rolbypassrls FROM pg_roles "
                "WHERE rolname IN ('agencyos_app', 'agencyos_worker')"
            )
            rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    finally:
        conn.close()
    assert rows.get("agencyos_app") == (False, False)
    assert rows.get("agencyos_worker") == (False, True)


def test_owner_connection_unaffected_without_tenant_context(seeded_db):
    # Pins the deliberate no-FORCE design: developer/CI owner connections
    # keep working; production traffic uses the agencyos_app role instead.
    conn = _connect(seeded_db)
    try:
        assert _scalar(conn, "SELECT count(*) FROM public.users") == 2
        assert _scalar(conn, "SELECT public.tenant_org_id()") is None
    finally:
        conn.close()


def test_app_role_sees_nothing_without_tenant_context(seeded_db):
    conn = _connect(seeded_db, "agencyos_app")
    try:
        assert _scalar(conn, "SELECT public.tenant_org_id()") is None
        for table in ("organizations", "users", "leads", "refresh_tokens", "team_invites"):
            count = _scalar(conn, f"SELECT count(*) FROM public.{table}")
            assert count == 0, f"agencyos_app leaked {count} rows from {table} with no GUC"
    finally:
        conn.close()


def test_app_role_sees_only_guc_tenant(seeded_db):
    conn = _connect(seeded_db, "agencyos_app")
    try:
        _set_guc(conn, ORG_A)
        assert _scalar(conn, "SELECT id FROM public.users") == uuid.UUID(USER_A)
        assert _scalar(conn, "SELECT id FROM public.leads") == uuid.UUID(LEAD_A)
        assert _scalar(conn, "SELECT id FROM public.organizations") == uuid.UUID(ORG_A)

        _set_guc(conn, ORG_B)
        assert _scalar(conn, "SELECT id FROM public.users") == uuid.UUID(USER_B)
        assert _scalar(conn, "SELECT id FROM public.leads") == uuid.UUID(LEAD_B)
        assert _scalar(conn, "SELECT id FROM public.organizations") == uuid.UUID(ORG_B)
    finally:
        conn.close()


def test_cross_org_insert_rejected_same_org_insert_allowed(seeded_db):
    conn = _connect(seeded_db, "agencyos_app")
    _set_guc(conn, ORG_A)

    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege) as exc_info:
            cur.execute(
                "INSERT INTO public.users (organization_id, email, full_name) "
                "VALUES (%s, %s, %s)",
                (ORG_B, "intruder@example.com", "Intruder"),
            )
        assert exc_info.value.pgcode == "42501"

        # Positive control: the same role writes its OWN tenant fine.
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name) "
            "VALUES (%s, %s, %s)",
            (ORG_A, "new-member@example.com", "New Member"),
        )
    conn.close()


def test_cross_org_update_and_delete_are_invisible(seeded_db):
    conn = _connect(seeded_db, "agencyos_app")
    _set_guc(conn, ORG_A)

    with conn.cursor() as cur:
        cur.execute("UPDATE public.users SET full_name = 'Hacked' WHERE id = %s", (USER_B,))
        assert cur.rowcount == 0
        cur.execute("DELETE FROM public.users WHERE id = %s", (USER_B,))
        assert cur.rowcount == 0
        # Moving an own row across tenants violates WITH CHECK.
        with pytest.raises(psycopg2.errors.InsufficientPrivilege) as exc_info:
            cur.execute(
                "UPDATE public.users SET organization_id = %s WHERE id = %s",
                (ORG_B, USER_A),
            )
        assert exc_info.value.pgcode == "42501"
    conn.close()

    # And the target tenant's data really is untouched.
    assert _owner_scalar(seeded_db, "SELECT full_name FROM public.users WHERE id = %s",
                         (USER_B,)) == "User B"


def test_worker_role_bypasses_rls_and_sees_all_tenants(seeded_db):
    conn = _connect(seeded_db, "agencyos_worker")
    try:
        assert _scalar(conn, "SELECT count(*) FROM public.organizations") == 2
        assert _scalar(conn, "SELECT count(*) FROM public.users") == 2
        assert _scalar(conn, "SELECT count(*) FROM public.leads") == 2
    finally:
        conn.close()


def test_definer_lookups_see_through_rls_without_tenant_context(seeded_db):
    """Auth must work before identity exists: plain SELECTs see nothing,
    the SECURITY DEFINER lookups still resolve the right tenant rows."""
    conn = _connect(seeded_db, "agencyos_app")  # deliberately no GUC
    try:
        assert _scalar(
            conn, "SELECT count(*) FROM public.users WHERE email = %s",
            ("userb@example.com",),
        ) == 0, "plain SELECT must be RLS-blocked with no tenant context"

        assert _scalar(
            conn, "SELECT id FROM public.app_get_user_by_email(%s)",
            ("userb@example.com",),
        ) == uuid.UUID(USER_B)
        assert _scalar(
            conn, "SELECT organization_id FROM public.app_find_active_user_by_email(%s)",
            ("userb@example.com",),
        ) == uuid.UUID(ORG_B)
        assert _scalar(
            conn, "SELECT id FROM public.app_get_user_by_id(%s)", (USER_B,)
        ) == uuid.UUID(USER_B)
        assert _scalar(
            conn, "SELECT id FROM public.app_get_organization_by_slug(%s)",
            ("org-beta",),
        ) == uuid.UUID(ORG_B)

        assert _scalar(conn, "SELECT public.app_slug_available(%s)", ("org-alpha",)) is False
        assert _scalar(conn, "SELECT public.app_slug_available(%s)", ("fresh-slug-1",)) is True

        assert _scalar(
            conn, "SELECT id FROM public.app_get_team_invite_by_token_hash(%s)",
            (INVITE_TOKEN_A,),
        ) == uuid.UUID("00000000-0000-0000-0000-0000000000a7")
        assert _scalar(
            conn, "SELECT id FROM public.app_get_valid_refresh_token(%s, now())",
            (REFRESH_TOKEN_A,),
        ) == uuid.UUID("00000000-0000-0000-0000-0000000000a6")
    finally:
        conn.close()


def test_tenant_org_id_semantics(seeded_db):
    conn = _connect(seeded_db, "agencyos_app")
    try:
        assert _scalar(conn, "SELECT public.tenant_org_id()") is None
        _set_guc(conn, "")
        assert _scalar(conn, "SELECT public.tenant_org_id()") is None
        _set_guc(conn, ORG_A)
        assert str(_scalar(conn, "SELECT public.tenant_org_id()")) == ORG_A
        _set_guc(conn, "not-a-uuid")
        assert _scalar(conn, "SELECT public.tenant_org_id()") is None
    finally:
        conn.close()


def test_guc_does_not_leak_across_connections(seeded_db):
    conn1 = _connect(seeded_db, "agencyos_app")
    conn2 = _connect(seeded_db, "agencyos_app")
    try:
        _set_guc(conn1, ORG_A)
        assert _scalar(conn1, "SELECT count(*) FROM public.users") == 1
        # A brand-new session carries no tenant context from conn1.
        assert _scalar(conn2, "SELECT public.tenant_org_id()") is None
        assert _scalar(conn2, "SELECT count(*) FROM public.users") == 0
    finally:
        conn1.close()
        conn2.close()


# --- end-to-end through the real application stack (async) ----------------


async def test_async_auth_flow_enforced_by_rls(seeded_db):
    """Register/login/get_current_user through AuthService + deps while the
    connection runs as ``agencyos_app`` under RLS with the production
    transaction-begin listener attached. Any missing activate_org call in the
    auth path fails here as SQLSTATE 42501 or as an empty result."""
    set_current_organization_id(None)
    engine = create_async_engine(_async_url_for(seeded_db), poolclass=NullPool)
    event.listen(engine.sync_engine, "begin", _restore_tenant_guc)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    email = f"rls-owner-{uuid.uuid4().hex[:8]}@example.com"
    access = ""
    try:
        async with factory() as session:
            await session.exec_driver_sql("SET ROLE agencyos_app")
            result = await AuthService(session).register(
                RegisterRequest(
                    email=email,
                    password="S3cure!pass",
                    full_name="RLS Owner",
                    organization_name="RLS Org",
                    organization_slug=f"rls-{uuid.uuid4().hex[:8]}",
                )
            )
            access = result.access_token
            assert result.user.id

        org_id = _owner_scalar(
            seeded_db,
            "SELECT organization_id::text FROM public.users WHERE email = %s",
            (email,),
        )
        assert org_id

        # login: definer email lookup + token issuance must work under RLS.
        async with factory() as session:
            await session.exec_driver_sql("SET ROLE agencyos_app")
            logged = await AuthService(session).login(
                LoginRequest(email=email, password="S3cure!pass")
            )
            assert logged.access_token
            access = logged.access_token

        # get_current_user: definer load + activation.
        async with factory() as session:
            await session.exec_driver_sql("SET ROLE agencyos_app")
            user = await get_current_user(
                db=session,
                credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=access),
            )
            assert user.email == email

        # No tenant context: the same app role must see zero rows.
        set_current_organization_id(None)
        async with factory() as session:
            await session.exec_driver_sql("SET ROLE agencyos_app")
            count = (await session.execute(
                sa_text("SELECT count(*) FROM public.users")
            )).scalar_one()
            assert count == 0, "RLS hid the tenant leak: app role saw rows with no GUC"

        # Activated: sees its own tenant again (and only its own).
        async with factory() as session:
            await session.exec_driver_sql("SET ROLE agencyos_app")
            await activate_org(session, org_id)
            count = (await session.execute(
                sa_text("SELECT count(*) FROM public.users")
            )).scalar_one()
            assert count == 1
            row_org = (await session.execute(
                sa_text("SELECT organization_id::text FROM public.users WHERE email = :email"),
                {"email": email},
            )).scalar_one()
            assert row_org == org_id
    finally:
        set_current_organization_id(None)
        await engine.dispose()
