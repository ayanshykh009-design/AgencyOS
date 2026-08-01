"""Integration tests: apply the SQL migrations to a real PostgreSQL database
and verify the constraints, enums, triggers, and duplicate protection.

These tests are skipped automatically when no PostgreSQL server is reachable
(local dev without the docker compose postgres service). They run in a
disposable database that is dropped on teardown.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

pytest.importorskip("psycopg2")
import psycopg2  # noqa: E402
from psycopg2 import errors, sql  # noqa: E402

from app.core.config import settings  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations"
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


def _migration_files() -> list[Path]:
    return sorted(
        Path(MIGRATIONS_DIR).glob("[0-9][0-9][0-9][0-9]_*.sql"),
        key=lambda p: p.name,
    )


def _insert_org(conn: psycopg2.extensions.connection, org_id: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("INSERT INTO public.organizations (id, name, slug) VALUES (%s, %s, %s)"),
            (org_id or str(uuid.uuid4()), "Test Org", f"test-{uuid.uuid4().hex[:8]}"),
        )
    conn.commit()


@pytest.fixture()
def migrated_db():
    """Create a disposable database, apply all migrations, yield a connection."""
    admin = psycopg2.connect(ADMIN_URL)
    admin.autocommit = True
    db_name = f"agencyos_test_{uuid.uuid4().hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    conn = None
    try:
        params = admin.get_dsn_parameters()
        params["dbname"] = db_name
        conn = psycopg2.connect(**params)
        # Mirror scripts/db/migrate.sh: schema_migrations is a bootstrap table
        # created by the migration tooling, not by any migration file.
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
            cur.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db_name)))
        admin.close()


def test_migrations_apply_cleanly(migrated_db) -> None:
    expected = {
        "organizations", "users", "lead_sources", "leads", "lead_research",
        "outreach_messages", "outreach_attempts", "follow_ups",
        "manual_outreach_queue", "conversations", "conversation_messages",
        "activity_logs", "import_jobs", "import_row_errors", "provider_usage",
        "schema_migrations",
    }
    with migrated_db.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        tables = {row[0] for row in cur.fetchall()}
    assert expected <= tables


def test_duplicate_email_same_org_rejected(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.leads (organization_id, email) VALUES (%s, %s)",
            (ORG_ID, "dup@example.com"),
        )
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.leads (organization_id, email) VALUES (%s, %s)",
                (ORG_ID, "DUP@example.com"),
            )
    migrated_db.rollback()


def test_same_email_different_org_allowed(migrated_db) -> None:
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    _insert_org(migrated_db, org_a)
    _insert_org(migrated_db, org_b)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.leads (organization_id, email) VALUES (%s, %s), (%s, %s)",
            (org_a, "shared@example.com", org_b, "shared@example.com"),
        )
    migrated_db.commit()


def test_duplicate_phone_vs_whatsapp_rejected(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.leads (organization_id, phone) VALUES (%s, %s)",
            (ORG_ID, "+1 212 555 0142"),
        )
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.leads (organization_id, whatsapp) VALUES (%s, %s)",
                (ORG_ID, "12125550142"),
            )
    migrated_db.rollback()


def test_duplicate_website_domain_rejected(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.leads (organization_id, website) VALUES (%s, %s)",
            (ORG_ID, "https://www.Example.com/path"),
        )
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.leads (organization_id, website) VALUES (%s, %s)",
                (ORG_ID, "example.com"),
            )
    migrated_db.rollback()


def test_invalid_enum_value_rejected(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        with pytest.raises(errors.InvalidTextRepresentation):
            cur.execute(
                "INSERT INTO public.users (organization_id, email, full_name, role) "
                "VALUES (%s, %s, %s, %s)",
                (ORG_ID, "admin@example.com", "Admin", "superuser"),
            )
    migrated_db.rollback()


def test_check_constraint_score_range(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        with pytest.raises(errors.CheckViolation):
            cur.execute(
                "INSERT INTO public.leads (organization_id, email, score) VALUES (%s, %s, %s)",
                (ORG_ID, "score@example.com", 150),
            )
    migrated_db.rollback()


def test_org_delete_cascades_to_leads(migrated_db) -> None:
    org_id = str(uuid.uuid4())
    _insert_org(migrated_db, org_id)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.leads (organization_id, email) VALUES (%s, %s)",
            (org_id, "cascade@example.com"),
        )
        cur.execute("DELETE FROM public.organizations WHERE id = %s", (org_id,))
        cur.execute("SELECT count(*) FROM public.leads WHERE organization_id = %s", (org_id,))
        assert cur.fetchone()[0] == 0
    migrated_db.commit()


def test_generated_normalized_columns(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.leads (organization_id, email, phone, website) "
            "VALUES (%s, %s, %s, %s) RETURNING email_normalized, phone_normalized, website_domain",
            (ORG_ID, "ada@example.com", "+44 (20) 1234-5678", "https://www.Example.com/path"),
        )
        row = cur.fetchone()
        assert row == ("ada@example.com", "442012345678", "example.com")
    migrated_db.commit()


def test_lead_research_one_to_one(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.leads (organization_id, email) VALUES (%s, %s) RETURNING id",
            (ORG_ID, "research@example.com"),
        )
        lead_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.lead_research (lead_id, organization_id) VALUES (%s, %s)",
            (lead_id, ORG_ID),
        )
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.lead_research (lead_id, organization_id) VALUES (%s, %s)",
                (lead_id, ORG_ID),
            )
    migrated_db.rollback()


def test_provider_usage_daily_unique(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.provider_usage "
            "(organization_id, provider, feature, usage_date) VALUES (%s, %s, %s, %s)",
            (ORG_ID, "openai", "research", "2026-08-01"),
        )
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.provider_usage "
                "(organization_id, provider, feature, usage_date) VALUES (%s, %s, %s, %s)",
                (ORG_ID, "openai", "research", "2026-08-01"),
            )
    migrated_db.rollback()


def test_updated_at_trigger_refreshes(migrated_db) -> None:
    _insert_org(migrated_db)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.organizations (name, slug) "
            "VALUES (%s, %s) RETURNING id, updated_at",
            ("Trigger Org", f"trigger-{uuid.uuid4().hex[:8]}"),
        )
        org_id, before = cur.fetchone()
        cur.execute(
            "UPDATE public.organizations SET name = %s WHERE id = %s RETURNING updated_at",
            ("Trigger Org 2", org_id),
        )
        after = cur.fetchone()[0]
        assert after > before
    migrated_db.commit()
