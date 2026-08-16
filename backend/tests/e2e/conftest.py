"""Shared fixtures for the M10 end-to-end journey tests.

Mirrors the disposable-database setup used by the schema integration tests so
the critical-journey smoke can run against a real PostgreSQL in CI (and skip
gracefully where none is reachable).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pytest.importorskip("psycopg2")
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402

from _pg_helpers import dsn_for_database  # noqa: E402
from app.core.config import settings  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"
ADMIN_URL = os.getenv(
    "TEST_POSTGRES_URL",
    settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres",
)
ORG_ID = "00000000-0000-0000-0000-000000000001"


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
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _insert_org(conn, org_id: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "INSERT INTO public.organizations (id, name, slug) VALUES (%s, %s, %s)"
            ),
            (org_id or str(uuid.uuid4()), "Test Org", f"test-{uuid.uuid4().hex[:8]}"),
        )
    conn.commit()


@pytest.fixture()
def migrated_db():
    """Create a disposable database, apply all migrations, yield a connection."""
    admin = psycopg2.connect(ADMIN_URL)
    admin.autocommit = True
    db_name = f"agencyos_e2e_{uuid.uuid4().hex[:8]}"
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
        yield conn
    finally:
        if conn is not None:
            conn.close()
        with admin.cursor() as cur:
            cur.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db_name))
            )
        admin.close()
