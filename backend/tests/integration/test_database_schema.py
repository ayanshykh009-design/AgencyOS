"""Integration tests: apply the SQL migrations to a real PostgreSQL database
and verify the constraints, enums, triggers, and duplicate protection.

These tests are skipped automatically when no PostgreSQL server is reachable
(local dev without the docker compose postgres service). They run in a
disposable database that is dropped on teardown.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import DateTime  # noqa: E402

pytest.importorskip("psycopg2")
import psycopg2  # noqa: E402
from psycopg2 import errors, sql  # noqa: E402

from _pg_helpers import (  # noqa: E402
    dsn_for_database,
    ensure_compat_roles,
    enum_bootstrap_files,
)
from app.core.config import settings  # noqa: E402
from app.models.approval_request import ApprovalRequest  # noqa: E402
from app.models.enums import InviteStatus, UserRole  # noqa: E402
from app.models.refresh_token import RefreshToken  # noqa: E402
from app.models.team_invite import TeamInvite  # noqa: E402
from app.models.user import User  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations"
POLICIES_DIR = Path(__file__).resolve().parents[3] / "database" / "supabase" / "policies"
SCHEMA_DIR = Path(__file__).resolve().parents[3] / "database" / "schema"
ADMIN_URL = os.getenv(
    "TEST_POSTGRES_URL",
    settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres",
)

ORG_ID = "00000000-0000-0000-0000-000000000001"

# Digests of every SQL migration (LF-normalized, utf-8). M10 pins all
# migrations so a content change fails CI loudly instead of silently drifting
# the schema contract. Compute with:
#   python - <<'PY'
#   import hashlib, pathlib
#   for p in sorted((pathlib.Path(__file__).resolve().parents[3] /
#                   "database" / "migrations").glob("*.sql")):
#       print(p.name, hashlib.sha256(
#           p.read_bytes().replace(b"\r\n", b"\n")).hexdigest())
#   PY
EXPECTED_MIGRATION_SHAS = {
    "0001_core_enums.sql": ("d7f6a2d73496941edf7ec7afff8393218689447a585e5e30c3d688710f1ccea9"),
    "0002_tenant_identity.sql": (
        "0973f86e2613831fc1dd07e0ad730f9aa5b833fb849e49a66148a64dce4910b3"
    ),
    "0003_lead_tables.sql": ("a2af0f29dde779deaa6d521d6881a684f3d451c41dfb979c34b53e42dea7ab8c"),
    "0004_outreach_tables.sql": (
        "2cedda862a55f156020b16fe095a11a7c9ec27c5e0e404580124c2dd2015bf1c"
    ),
    "0005_conversations_activity.sql": (
        "e681d210fc9e506f28519dce8bfdffcd590a5de0ea5eb3ea8bf5417811a725ba"
    ),
    "0006_imports_provider.sql": (
        "35fde0c2f7e19a7ec91f6d4977e0ed2aa018d7a17aa2d9cd94009134f4ae43f6"
    ),
    "0007_auth.sql": ("85b13573becc50de037b5ea7a02af687a89be2372e39168c67e1413f3bd9587b"),
    "0008_team_management.sql": (
        "afc27c6bc12bff8fa5b593ce040ac70456077d291b35eb7d093aefa112e6f97e"
    ),
    "0009_lead_assignment.sql": (
        "1af8cad6a1bfca32677430f396bb5f5f02ce4fd0eaf047eb05f623d7ea0a0cdf"
    ),
    "0010_pipeline_management.sql": (
        "01efb962859eb1f2175c6972f595966007df1c29d9f9aa1a51641d2b203512c6"
    ),
    "0011_tasks.sql": ("e14fbca185e5c2fbd5ca5395570075f86f687aa539bfbc1589da0c71a69757f8"),
    "0012_notes.sql": ("737769feece03ac7e434000ced8ab045a805f2f292ba3fdec167ce7a227fcf00"),
    "0013_automation.sql": ("16f0a5f6b5810a38c68b07f7f8f9fc8ab6f37c8300e9553765b633d964c6e435"),
    "0014_schedule_last_fired.sql": (
        "a7a65004c360206a14940fb8b59cb68a58176d2539381f27877e49cae44fcebe"
    ),
    "0015_credential_key_versions.sql": (
        "7f29251cc33faa947e6fe7aa81e462733ca60543f8def76fb2a39f1e263bcd2e"
    ),
    "0016_search_trigram_indexes.sql": (
        "6db58d884d91d4f299f5f66be708a737e0ae6c5578d764c67e92746fc3e6fdf1"
    ),
    "0017_automation_hardening.sql": (
        "fdcd3f9fb596db2f29eeee7cbbedcfe32cc550a7dfda7579c230f3c28459fc08"
    ),
    "0018_phase5d_database_layer.sql": (
        "86e1bc090b3f8e232c2233d63df863deb6e1fb19e8dcc4e97d1612871ce0c4f1"
    ),
    "0019_phase5d_agent_runtime.sql": (
        "cf7a1c61c73d00c50398b3df99b88f54b39005d5b29a76296a0df7390fc0d507"
    ),
    "0020_m6_delivery.sql": ("dee39fa4d630ffed972d555b302fc86429736e24afd71ddcd0e1a502e621e084"),
    "0021_m6_delivery_hardening.sql": (
        "114d70dd991dcbcd5ee6d898bbef088fb29024bd5e7f7716c22dd4e394932f74"
    ),
    "0022_m7_growth_analyses.sql": (
        "8dbd759ab8f149a559b2bf6c8e1b5cec16aa871217f61e4f2011ffa596f8f4ce"
    ),
    "0023_m7_growth_forecasts_extended.sql": (
        "133be989d95010b3770f86635c6127baafde7f796e800a30936874c84999bd00"
    ),
    "0024_m7_growth_scenarios.sql": (
        "c0d0f76c73809992a132aa8b2f40d1dc8e1c793085d7112646d11942d538b9c7"
    ),
    "0025_m7_growth_recommendations.sql": (
        "243b55f437fa384fcef9e563db2488f79a6a061cf63d41ac0acd3bf96f22d051"
    ),
    "0026_m8_founder_assistant.sql": (
        "727cdd256393a39aca4ff23338774849fd2748a90999afd1d4fec31fb27d3123"
    ),
    "0027_m9_intelligence_signals.sql": (
        "c30e9dbd8150cd39de0ac5ce47663b9fb88cedff1c1994ddf4b7807dcb09d263"
    ),
    "0028_m11_ai_run_trace.sql": (
        "c89a344871ee97d6a77c1038c9dde609413cf640622c65377b3042459250a522"
    ),
    "0029_datetime_timezone_alignment.sql": (
        "02329addbedca81e6f6e4158746e96c7aa8a4d4894657040f1722a35b53b6d53"
    ),
    "0030_fix_founder_messages_metadata_column.sql": (
        "512848f0ecc1f673aa90b2c2e38e5a052fb0c02cab1935756912112d455a342b"
    ),
    "0031_fix_users_email_global_unique.sql": (
        "f8c04de960393dcb1835037cb0038d1c73cde36be7bfe9b1da26f07bd9fd08e6"
    ),
}


def _database_available() -> bool:
    try:
        conn = psycopg2.connect(ADMIN_URL, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _database_available(), reason="PostgreSQL server not reachable")


def _migration_files() -> list[Path]:
    # Canonical order: enum bootstrap first, then numbered migrations. Mirrors
    # scripts/db/migrate.sh (enum files whose types are not created inline by a
    # numbered migration are applied before the numbered migrations run).
    return enum_bootstrap_files() + sorted(
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
    ensure_compat_roles(ADMIN_URL)
    db_name = f"agencyos_test_{uuid.uuid4().hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    conn = None
    try:
        conn = psycopg2.connect(dsn_for_database(ADMIN_URL, db_name))
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


def test_per_test_db_connection_preserves_password_auth(migrated_db) -> None:
    # Regression for BASELINE-DB-001: the per-test database connection must
    # authenticate with the password carried by ADMIN_URL (NOT the password-less
    # dict produced by get_dsn_parameters()). A successful query here proves the
    # connection used password auth, and the migrated table proves migrations
    # were applied to this disposable database via that same authenticated
    # connection.
    with migrated_db.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {row[0] for row in cur.fetchall()}
    assert "schema_migrations" in tables


def test_compat_roles_bootstrapped_before_migrations(migrated_db) -> None:
    # Regression for BASELINE-DB-002: the test/CI Postgres environment must
    # provision the Supabase compatibility roles (anon, authenticated) referenced
    # by 0007_auth.sql (REVOKE ... FROM anon, authenticated) and RLS policies
    # (FOR ... TO authenticated) BEFORE migrations run. Without them, migration
    # application fails with `role "anon" does not exist` and every downstream
    # table is missing. The fact that this test's ``migrated_db`` fixture setup
    # succeeded already proves the bootstrap ran; here we assert the contract
    # explicitly, that a REPEATED bootstrap invocation is safe (idempotent), and
    # that the exact previously-failing statement is now a no-op.
    ensure_compat_roles(ADMIN_URL)  # second call must not raise

    with migrated_db.cursor() as cur:
        cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        roles = {row[0] for row in cur.fetchall()}
        assert roles == {"anon", "authenticated"}, roles

        # The exact statement that previously raised UndefinedObject must now be
        # idempotent (roles exist).
        cur.execute("REVOKE SELECT (password_hash) ON public.users FROM anon, authenticated")
        migrated_db.commit()

        # Core auth tables created by the migration sequence must exist.
        cur.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' "
            "AND tablename IN ('organizations', 'users')"
        )
        tables = {row[0] for row in cur.fetchall()}
        assert tables == {"organizations", "users"}, tables


def test_migrations_apply_cleanly(migrated_db) -> None:
    expected = {
        "organizations",
        "users",
        "lead_sources",
        "leads",
        "lead_research",
        "outreach_messages",
        "outreach_attempts",
        "follow_ups",
        "manual_outreach_queue",
        "conversations",
        "conversation_messages",
        "activity_logs",
        "import_jobs",
        "import_row_errors",
        "provider_usage",
        "schema_migrations",
        "workflows",
        "workflow_triggers",
        "workflow_executions",
        "workflow_events",
        "credentials",
        "credential_key_versions",
        "execution_events",
        "worker_health",
        "system_settings",
        "ai_memories",
        "knowledge_items",
        "agent_runs",
        "agent_state",
        "notifications",
        "approval_requests",
        "approval_logs",
        "briefings",
        "growth_metrics",
        "growth_forecasts",
        "business_insights",
        "intelligence_signals",
    }
    with migrated_db.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {row[0] for row in cur.fetchall()}
    assert expected <= tables


def test_duplicate_email_same_org_rejected(migrated_db) -> None:
    _insert_org(migrated_db, ORG_ID)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.leads (organization_id, email) VALUES (%s, %s)",
            (ORG_ID, "dup@example.com"),
        )
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.leads (organization_id, email) VALUES (%s, %s)",
                (ORG_ID, "dup@example.com"),
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
    _insert_org(migrated_db, ORG_ID)
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
    _insert_org(migrated_db, ORG_ID)
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
    _insert_org(migrated_db, ORG_ID)
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
    _insert_org(migrated_db, ORG_ID)
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
    _insert_org(migrated_db, ORG_ID)
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


def test_migration_0014_schedule_last_fired_additive_idempotent(migrated_db) -> None:
    """0014 adds last_fired_at additively; re-applying is a no-op, zero data loss."""
    with migrated_db.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'workflow_triggers' "
            "AND column_name = 'last_fired_at')"
        )
        assert cur.fetchone()[0] is True
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
            "AND tablename = 'workflow_triggers' "
            "AND indexname = 'idx_workflow_triggers_schedule_due'"
        )
        assert cur.fetchone() is not None

    org_id = str(uuid.uuid4())
    _insert_org(migrated_db, org_id)
    migration_0014 = (MIGRATIONS_DIR / "0014_schedule_last_fired.sql").read_text(encoding="utf-8")
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (org_id, "owner@example.com", "Owner", "owner"),
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.workflows "
            "(organization_id, name, status, execution_mode, created_by_user_id) "
            "VALUES (%s, %s, 'active', 'builtin', %s) RETURNING id",
            (org_id, "Daily sync", user_id),
        )
        workflow_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.workflow_triggers "
            "(organization_id, workflow_id, name, trigger_type, schedule_cron, enabled) "
            "VALUES (%s, %s, %s, 'schedule', '0 9 * * *', true) RETURNING id, last_fired_at",
            (org_id, workflow_id, "Morning run"),
        )
        trigger_id, last_fired_at = cur.fetchone()
        assert last_fired_at is None

        # Re-applying 0014 must be a safe no-op and must not touch the row.
        cur.execute(migration_0014)
        cur.execute(
            "SELECT name, last_fired_at FROM public.workflow_triggers WHERE id = %s",
            (trigger_id,),
        )
        assert cur.fetchone() == ("Morning run", None)
    migrated_db.commit()


def test_migration_0015_credential_key_versions_additive_idempotent(migrated_db) -> None:
    """0015 adds key_version/last_rotated_at + registry; re-applying is a no-op."""
    with migrated_db.cursor() as cur:
        for column in ("key_version", "last_rotated_at"):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'credentials' "
                "AND column_name = %s)",
                (column,),
            )
            assert cur.fetchone()[0] is True
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'credential_key_versions')"
        )
        assert cur.fetchone()[0] is True
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
            "AND tablename = 'credentials' "
            "AND indexname = 'idx_credentials_key_version'"
        )
        assert cur.fetchone() is not None

    org_id = str(uuid.uuid4())
    _insert_org(migrated_db, org_id)
    migration_0015 = (MIGRATIONS_DIR / "0015_credential_key_versions.sql").read_text(
        encoding="utf-8"
    )
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (org_id, "cred-owner@example.com", "Owner", "owner"),
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.credentials "
            "(organization_id, name, credential_type, encrypted_value, value_preview, "
            "created_by_user_id) "
            "VALUES (%s, %s, 'n8n_api_key', %s, %s, %s) RETURNING id, key_version",
            (org_id, "n8n prod", "enc:legacy", "abcd", user_id),
        )
        credential_id, key_version = cur.fetchone()
        assert key_version == "0"

        # Re-applying 0015 must be a safe no-op and must not touch the row.
        cur.execute(migration_0015)
        cur.execute(
            "SELECT name, key_version, encrypted_value FROM public.credentials WHERE id = %s",
            (credential_id,),
        )
        assert cur.fetchone() == ("n8n prod", "0", "enc:legacy")
    migrated_db.commit()


def test_migration_0017_automation_hardening_additive_idempotent(migrated_db) -> None:
    """0017 adds the execution timeline/heartbeat/settings tables + queue columns.

    Re-applying must be a no-op that does not touch existing rows.
    """
    with migrated_db.cursor() as cur:
        for table in ("execution_events", "worker_health", "system_settings"):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s)",
                (table,),
            )
            assert cur.fetchone()[0] is True
        for column in ("cancel_requested_at", "cancelled_by_user_id", "idempotency_key"):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'workflow_executions' "
                "AND column_name = %s)",
                (column,),
            )
            assert cur.fetchone()[0] is True
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' "
            "AND tablename = 'workflow_executions' "
            "AND indexname = 'uq_workflow_executions_org_idempotency')"
        )
        assert cur.fetchone()[0] is True
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_type t "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'public' AND t.typname = 'execution_event_type')"
        )
        assert cur.fetchone()[0] is True
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'activity_event_type' AND e.enumlabel = 'automation_paused')"
        )
        assert cur.fetchone()[0] is True

    org_id = str(uuid.uuid4())
    _insert_org(migrated_db, org_id)
    migration_0017 = (MIGRATIONS_DIR / "0017_automation_hardening.sql").read_text(encoding="utf-8")
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (org_id, "hardening-owner@example.com", "Owner", "owner"),
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.workflows "
            "(organization_id, name, status, execution_mode, created_by_user_id) "
            "VALUES (%s, %s, 'active', 'builtin', %s) RETURNING id",
            (org_id, "Hardening wf", user_id),
        )
        workflow_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.workflow_executions "
            "(organization_id, workflow_id, status, idempotency_key) "
            "VALUES (%s, %s, 'queued', %s) RETURNING id, cancel_requested_at",
            (org_id, workflow_id, "idem-key-1"),
        )
        execution_id, cancel_requested_at = cur.fetchone()
        assert cancel_requested_at is None
        cur.execute(
            "INSERT INTO public.execution_events "
            "(organization_id, workflow_id, execution_id, attempt, event_type) "
            "VALUES (%s, %s, %s, 0, 'queued') RETURNING id",
            (org_id, workflow_id, execution_id),
        )
        event_id = cur.fetchone()[0]
        assert event_id is not None
        cur.execute(
            "INSERT INTO public.system_settings (key, value) "
            "VALUES ('automation.control', %s::jsonb) RETURNING key",
            ('{"paused": false}',),
        )
        assert cur.fetchone()[0] == "automation.control"

        # Re-applying 0017 must be a safe no-op and must not touch existing rows.
        cur.execute(migration_0017)
        cur.execute(
            "SELECT status, idempotency_key FROM public.workflow_executions WHERE id = %s",
            (execution_id,),
        )
        assert cur.fetchone() == ("queued", "idem-key-1")
    migrated_db.commit()


def test_migration_0017_idempotency_unique_per_org(migrated_db) -> None:
    """Duplicate idempotency keys are rejected within one org, allowed across."""
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    _insert_org(migrated_db, org_a)
    _insert_org(migrated_db, org_b)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (org_a, "idem-a@example.com", "Owner A", "owner"),
        )
        user_a = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (org_b, "idem-b@example.com", "Owner B", "owner"),
        )
        user_b = cur.fetchone()[0]
        for org, user, suffix in ((org_a, user_a, "a"), (org_b, user_b, "b")):
            cur.execute(
                "INSERT INTO public.workflows "
                "(organization_id, name, status, execution_mode, created_by_user_id) "
                "VALUES (%s, %s, 'active', 'builtin', %s) RETURNING id",
                (org, f"Wf {suffix}", user),
            )
            workflow_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO public.workflow_executions "
                "(organization_id, workflow_id, status, idempotency_key) "
                "VALUES (%s, %s, 'queued', 'shared-key')",
                (org, workflow_id),
            )
        # Same org + same key -> unique violation.
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.workflow_executions "
                "(organization_id, workflow_id, status, idempotency_key) "
                "VALUES (%s, %s, 'queued', 'shared-key')",
                (org_a, workflow_id),
            )
    migrated_db.rollback()


def test_migration_0018_phase5d_database_layer_additive_idempotent(migrated_db) -> None:
    """0018 adds the AI layer tables + enums + indexes.

    Re-applying must be a no-op that does not touch existing rows.
    """
    with migrated_db.cursor() as cur:
        for table in (
            "ai_memories",
            "knowledge_items",
            "agent_runs",
            "agent_state",
            "notifications",
            "approval_requests",
            "approval_logs",
            "briefings",
            "growth_metrics",
            "growth_forecasts",
            "business_insights",
        ):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s)",
                (table,),
            )
            assert cur.fetchone()[0] is True
        for enum_name in (
            "memory_type",
            "memory_scope",
            "agent_run_status",
            "agent_run_trigger",
            "agent_state_status",
            "agent_health",
            "notification_type",
            "approval_request_status",
            "approval_log_action",
            "briefing_type",
            "insight_type",
            "insight_severity",
            "insight_status",
            "signal_category",
            "signal_source_type",
            "intelligence_signal_status",
            "intelligence_signal_severity",
            "intelligence_confidence",
        ):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' AND t.typname = %s)",
                (enum_name,),
            )
            assert cur.fetchone()[0] is True
        for index in (
            "idx_ai_memories_working_ttl",
            "uq_agent_state_org_agent",
            "idx_notifications_user_unread",
            "idx_approval_requests_pending_expiry",
            "idx_approval_logs_org_occurred",
            "uq_growth_metrics_org_type_period",
            "idx_business_insights_source",
            "uq_intelligence_signals_org_hash_active",
            "idx_intelligence_signals_org_status_priority",
            "idx_intelligence_signals_org_source",
            "idx_intelligence_signals_org_created",
        ):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = %s)",
                (index,),
            )
            assert cur.fetchone()[0] is True
        # approval_logs is append-only: no updated_at column.
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'approval_logs' "
            "AND column_name = 'updated_at')"
        )
        assert cur.fetchone()[0] is False
        # RLS is enabled on every new table.
        cur.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' "
            "AND rowsecurity = true AND tablename IN ("
            "'ai_memories', 'knowledge_items', 'agent_runs', 'agent_state', "
            "'notifications', 'approval_requests', 'approval_logs', 'briefings', "
            "'growth_metrics', 'growth_forecasts', 'business_insights', "
            "'intelligence_signals')"
        )
        assert cur.fetchone()[0] == 12

    org_id = str(uuid.uuid4())
    _insert_org(migrated_db, org_id)
    migration_0018 = (MIGRATIONS_DIR / "0018_phase5d_database_layer.sql").read_text(
        encoding="utf-8"
    )
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.ai_memories (organization_id, scope, content) "
            "VALUES (%s, 'research', 'memory row') RETURNING id, memory_type",
            (org_id,),
        )
        memory_id, memory_type = cur.fetchone()
        assert memory_type == "working"
        cur.execute(
            "INSERT INTO public.approval_requests (organization_id, title) "
            "VALUES (%s, 'approval row') RETURNING id, status",
            (org_id,),
        )
        approval_id, approval_status = cur.fetchone()
        assert approval_status == "pending"

        # Re-applying 0018 must be a safe no-op and must not touch existing rows.
        cur.execute(migration_0018)
        cur.execute(
            "SELECT scope, content FROM public.ai_memories WHERE id = %s",
            (memory_id,),
        )
        assert cur.fetchone() == ("research", "memory row")
        cur.execute(
            "SELECT title, status FROM public.approval_requests WHERE id = %s",
            (approval_id,),
        )
        assert cur.fetchone() == ("approval row", "pending")
    migrated_db.commit()


def test_retention_chunked_delete_respects_batch(migrated_db) -> None:
    """The retention sweep's chunked DELETE removes only old rows, in order.

    Mirrors ``app/workers/retention_worker.py``: delete up to ``batch`` events
    older than the cutoff, oldest first, repeating until the chunk is partial.
    """
    from datetime import UTC, datetime, timedelta

    org_id = str(uuid.uuid4())
    _insert_org(migrated_db, org_id)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (org_id, "retention@example.com", "Retention", "owner"),
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.workflows "
            "(organization_id, name, status, execution_mode, created_by_user_id) "
            "VALUES (%s, %s, 'active', 'builtin', %s) RETURNING id",
            (org_id, "Retention wf", user_id),
        )
        workflow_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.workflow_executions "
            "(organization_id, workflow_id, status) VALUES (%s, %s, 'queued') RETURNING id",
            (org_id, workflow_id),
        )
        execution_id = cur.fetchone()[0]

        old = datetime.now(UTC) - timedelta(days=100)
        new = datetime.now(UTC)
        for _, occurred_at in ((1, old), (2, old), (3, new)):
            cur.execute(
                "INSERT INTO public.execution_events "
                "(organization_id, workflow_id, execution_id, attempt, event_type, occurred_at) "
                "VALUES (%s, %s, %s, 0, 'queued', %s)",
                (org_id, workflow_id, execution_id, occurred_at),
            )

        cutoff = datetime.now(UTC) - timedelta(days=90)
        batch = 1
        total_deleted = 0
        while True:
            cur.execute(
                "DELETE FROM public.execution_events WHERE id IN ("
                "  SELECT id FROM public.execution_events"
                "  WHERE occurred_at < %s ORDER BY occurred_at LIMIT %s"
                ")",
                (cutoff, batch),
            )
            deleted = cur.rowcount
            total_deleted += deleted
            if deleted < batch:
                break
        assert total_deleted == 2
        cur.execute(
            "SELECT count(*) FROM public.execution_events WHERE occurred_at < %s",
            (cutoff,),
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT event_type FROM public.execution_events WHERE occurred_at >= %s",
            (cutoff,),
        )
        assert cur.fetchone()[0] == "queued"
    migrated_db.commit()


def test_worker_health_retention_prunes_dead_instances(migrated_db) -> None:
    """Long-gone worker heartbeat rows are pruned; live ones are kept."""
    from datetime import UTC, datetime, timedelta

    stale = datetime.now(UTC) - timedelta(days=200)
    fresh = datetime.now(UTC)
    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.worker_health "
            "(worker_type, instance_id, pid, hostname, last_heartbeat_at) "
            "VALUES ('execution', %s, 1, 'dead', %s)",
            (str(uuid.uuid4()), stale),
        )
        cur.execute(
            "INSERT INTO public.worker_health "
            "(worker_type, instance_id, pid, hostname, last_heartbeat_at) "
            "VALUES ('execution', %s, 2, 'alive', %s)",
            (str(uuid.uuid4()), fresh),
        )
        cur.execute(
            "DELETE FROM public.worker_health WHERE id IN ("
            "  SELECT id FROM public.worker_health"
            "  WHERE last_heartbeat_at < %s ORDER BY last_heartbeat_at LIMIT 100"
            ")",
            (stale + timedelta(days=1),),
        )
        cur.execute("SELECT count(*) FROM public.worker_health WHERE hostname = 'dead'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM public.worker_health WHERE hostname = 'alive'")
        assert cur.fetchone()[0] == 1
    migrated_db.commit()


def test_migration_0019_agent_runtime_additive_idempotent(migrated_db) -> None:
    """0019 adds queue-hardening columns + partial indexes to agent_runs.

    Re-applying must be a no-op that does not touch existing rows.
    """
    org_id = str(uuid.uuid4())
    _insert_org(migrated_db, org_id)
    with migrated_db.cursor() as cur:
        for column in ("cancel_requested_at", "cancelled_by_user_id", "idempotency_key"):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'agent_runs' "
                "AND column_name = %s)",
                (column,),
            )
            assert cur.fetchone()[0] is True
        for index in ("uq_agent_runs_org_idempotency", "idx_agent_runs_cancel_pending"):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' "
                "AND tablename = 'agent_runs' AND indexname = %s)",
                (index,),
            )
            assert cur.fetchone()[0] is True
        cur.execute(
            "INSERT INTO public.agent_runs "
            "(organization_id, agent_name, idempotency_key) "
            "VALUES (%s, %s, %s) RETURNING id, status, cancel_requested_at",
            (org_id, "founder_assistant", "runtime-idem-key-1"),
        )
        run_id, status, cancel_requested_at = cur.fetchone()
        assert status == "queued"
        assert cancel_requested_at is None

        migration_0019 = (MIGRATIONS_DIR / "0019_phase5d_agent_runtime.sql").read_text(
            encoding="utf-8"
        )
        # Re-applying 0019 must be a safe no-op and must not touch existing rows.
        cur.execute(migration_0019)
        cur.execute(
            "SELECT status, idempotency_key FROM public.agent_runs WHERE id = %s",
            (run_id,),
        )
        assert cur.fetchone() == ("queued", "runtime-idem-key-1")
    migrated_db.commit()


def test_migration_0019_idempotency_unique_per_org(migrated_db) -> None:
    """Duplicate agent-run idempotency keys are rejected within one org."""
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    _insert_org(migrated_db, org_a)
    _insert_org(migrated_db, org_b)
    with migrated_db.cursor() as cur:
        for org in (org_a, org_b):
            cur.execute(
                "INSERT INTO public.agent_runs "
                "(organization_id, agent_name, idempotency_key) "
                "VALUES (%s, 'outreach_agent', 'shared-key')",
                (org,),
            )
        # Same org + same key -> unique violation (mirrors uq_agent_runs_org_idempotency).
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.agent_runs "
                "(organization_id, agent_name, idempotency_key) "
                "VALUES (%s, 'outreach_agent', 'shared-key')",
                (org_a,),
            )
    migrated_db.rollback()


def _agent_runs_additions_0019() -> tuple[set[str], set[str]]:
    """Column and index names migration 0019 adds to ``public.agent_runs``.

    Derived from the migration (the schema source of truth) so the mirror
    parity guard tracks migration edits instead of hardcoding identifiers.
    """
    text = (MIGRATIONS_DIR / "0019_phase5d_agent_runtime.sql").read_text(encoding="utf-8")
    statements = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    columns = set(re.findall(r"ADD COLUMN IF NOT EXISTS\s+([a-z_]+)", statements))
    indexes = set(re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS\s+([a-z_]+)", statements))
    return columns, indexes


def test_agent_runs_schema_mirror_matches_0019() -> None:
    """The readable schema mirror must declare every M5/0019 addition.

    ``database/schema/agent_runs.sql`` is the canonical readable mirror of the
    agent_runs migrations (docs/database.md). This guard derives the additions
    from migration 0019 itself and requires the mirror to declare each one, so
    a future migration edit cannot silently leave the mirror stale.
    """
    added_columns, added_indexes = _agent_runs_additions_0019()
    assert added_columns and added_indexes, "0019 must declare the guarded additions"

    mirror = (SCHEMA_DIR / "agent_runs.sql").read_text(encoding="utf-8")
    table_body = re.search(
        r"CREATE TABLE IF NOT EXISTS public\.agent_runs \((?P<body>.*?)\n\);",
        mirror,
        re.DOTALL,
    )
    assert table_body, "schema mirror must define public.agent_runs"
    body = table_body.group("body")

    for column in sorted(added_columns):
        assert re.search(rf"(?m)^  {re.escape(column)}\b", body), (
            f"schema mirror missing column {column!r} added by migration 0019"
        )

    for index in sorted(added_indexes):
        assert re.search(
            rf"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS {re.escape(index)}\b",
            mirror,
        ), f"schema mirror missing index {index!r} created by migration 0019"


def _sha256(path: Path) -> str:
    import hashlib

    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def test_all_migrations_immutable_sha256() -> None:
    """M10 pins every migration's content so schema drift fails CI loudly.

    Compute the expected digests with the snippet in EXPECTED_MIGRATION_SHAS.
    """
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    found = {p.name: _sha256(p) for p in migration_files}
    assert set(found) == set(EXPECTED_MIGRATION_SHAS), (
        f"migration set changed; expected {sorted(EXPECTED_MIGRATION_SHAS)} got {sorted(found)}"
    )
    for name, digest in EXPECTED_MIGRATION_SHAS.items():
        assert found[name] == digest, f"migration content drift: {name}"


def test_migration_0018_unchanged_sha256() -> None:
    """M4 must not modify 0018: the migration content is pinned by digest."""
    raw = (MIGRATIONS_DIR / "0018_phase5d_database_layer.sql").read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    import hashlib

    assert (
        hashlib.sha256(normalized).hexdigest()
        == EXPECTED_MIGRATION_SHAS["0018_phase5d_database_layer.sql"]
    )


# BASELINE-DB-003: canonical automation enum contract. Values mirror
# database/schema/00_enums.sql and database/migrations/enums/10_automation.sql.
AUTOMATION_ENUM_CONTRACT = {
    "workflow_status": ["draft", "active", "paused", "archived"],
    "workflow_trigger_type": ["manual", "event", "schedule"],
    "execution_status": [
        "queued",
        "running",
        "succeeded",
        "failed",
        "retrying",
        "cancelled",
        "timed_out",
    ],
    "credential_type": ["n8n_api_key", "api_key", "basic_auth"],
}


def test_automation_enum_types_match_schema_contract(migrated_db) -> None:
    """BASELINE-DB-003 regression: 0013 must create its own enum types.

    The four automation enums must exist with exactly the canonical labels
    from ``database/schema/00_enums.sql`` before the workflow tables that
    reference them (the ``migrated_db`` fixture applying 0013 proves the
    ordering — a missing creation aborts fixture setup).
    """
    with migrated_db.cursor() as cur:
        for type_name, expected_labels in AUTOMATION_ENUM_CONTRACT.items():
            cur.execute(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' AND t.typname = %s "
                "ORDER BY e.enumsortorder",
                (type_name,),
            )
            found = [row[0] for row in cur.fetchall()]
            assert found == expected_labels, f"enum public.{type_name} labels drifted: {found}"

        # Workflow tables actually reference the migration-owned types.
        cur.execute(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'workflows' "
            "AND column_name = 'status'"
        )
        assert cur.fetchone()[0] == "workflow_status"
        cur.execute(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'credentials' "
            "AND column_name = 'credential_type'"
        )
        assert cur.fetchone()[0] == "credential_type"


def test_automation_enum_replay_is_idempotent(migrated_db) -> None:
    """BASELINE-DB-003 regression: re-applying 0013's guarded enum blocks.

    Replays the pg_type-guarded creation for every automation enum twice;
    the guard must skip existing types so replay neither errors nor
    duplicates labels (migration replay/idempotency contract).
    """
    replay = """
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'public' AND t.typname = %(type)s
      ) THEN
        EXECUTE format('CREATE TYPE public.%%I AS ENUM (''x'')', %(type)s);
      END IF;
    END;
    $$;
    """
    with migrated_db.cursor() as cur:
        for _round in (1, 2):
            for type_name in AUTOMATION_ENUM_CONTRACT:
                cur.execute(replay, {"type": type_name})
        for type_name, expected_labels in AUTOMATION_ENUM_CONTRACT.items():
            cur.execute(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' AND t.typname = %s "
                "ORDER BY e.enumsortorder",
                (type_name,),
            )
            assert [row[0] for row in cur.fetchall()] == expected_labels


FOUNDER_ENUM_CONTRACT = {
    "founder_message_sender": ["user", "assistant"],
    "founder_proposal_status": [
        "proposed",
        "approved",
        "denied",
        "expired",
        "cancelled",
        "executing",
        "succeeded",
        "failed",
    ],
    "founder_action_type": [
        "create_task",
        "draft_email",
        "send_email",
        "run_workflow",
        "export",
        "general",
    ],
}


def test_founder_enums_bootstrapped_before_dependent_migrations(migrated_db) -> None:
    """BASELINE-DB-003 regression: canonical enum bootstrap runs before 0026.

    The founder enums live only in database/migrations/enums/14_founder.sql and
    are never created inline by a numbered migration. The harness must apply
    that enum file (via ``enum_bootstrap_files``) before 0026_m8_founder_
    assistant.sql, otherwise the founder tables fail with
    ``type "public.founder_message_sender" does not exist``.
    """
    with migrated_db.cursor() as cur:
        for type_name, expected_labels in FOUNDER_ENUM_CONTRACT.items():
            cur.execute(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' AND t.typname = %s "
                "ORDER BY e.enumsortorder",
                (type_name,),
            )
            found = [row[0] for row in cur.fetchall()]
            assert found == expected_labels, f"enum public.{type_name} labels drifted: {found}"
        # Founder tables reference the bootstrapped enums.
        cur.execute(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'founder_messages' "
            "AND column_name = 'sender_type'"
        )
        assert cur.fetchone()[0] == "founder_message_sender"


def test_enum_bootstrap_covers_uncreated_enums() -> None:
    """BASELINE-DB-003: bootstrap applies only enums not created inline.

    The harness must apply enums/14_founder.sql and enums/10_automation.sql
    (types used by numbered migrations but never created inline), while
    skipping enum files whose types ARE created inline by numbered migrations
    (otherwise a ``type already exists`` collision aborts the run).
    """
    from _pg_helpers import enum_bootstrap_files

    names = {p.name for p in enum_bootstrap_files()}
    assert "14_founder.sql" in names
    assert "10_automation.sql" in names
    assert "01_channel.sql" not in names
    assert "07_assignment.sql" not in names
    assert "11_automation_hardening.sql" not in names
    assert "12_phase5d.sql" not in names
    assert "13_delivery.sql" not in names


def test_memory_cleanup_org_scoped_and_working_only(migrated_db) -> None:
    """The M4 cleanup sweep deletes only expired working rows for one org.

    Mirrors ``AiMemoryRepository.list_expired_working`` + ``delete_many``:
    org-scoped, ``memory_type='working'`` only, oldest first, batch-bounded.
    Long-term rows and other orgs must be untouched.
    """
    from datetime import UTC, datetime, timedelta

    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    _insert_org(migrated_db, org_a)
    _insert_org(migrated_db, org_b)

    now = datetime.now(UTC)
    old = now - timedelta(days=400)
    fresh = now - timedelta(days=1)
    with migrated_db.cursor() as cur:
        for org in (org_a, org_b):
            cur.execute(
                "INSERT INTO public.ai_memories "
                "(organization_id, memory_type, scope, content, created_at) "
                "VALUES (%s, 'working', 'research', 'expired row', %s)",
                (org, old),
            )
        # Fresh working row (not expired) + long-term row for org A.
        cur.execute(
            "INSERT INTO public.ai_memories "
            "(organization_id, memory_type, scope, content, created_at) "
            "VALUES (%s, 'working', 'research', 'fresh row', %s)",
            (org_a, fresh),
        )
        cur.execute(
            "INSERT INTO public.ai_memories "
            "(organization_id, memory_type, scope, content, metadata, created_at) "
            "VALUES (%s, 'long_term', 'manual', 'durable row', "
            '\'{"category": "founder"}\'::jsonb, %s)',
            (org_a, old),
        )

        cutoff = now - timedelta(days=30)
        batch = 100
        # One bounded, org-scoped sweep for org A only (delete_many semantics).
        while True:
            cur.execute(
                "DELETE FROM public.ai_memories WHERE organization_id = %s AND id IN ("
                "  SELECT id FROM public.ai_memories"
                "  WHERE organization_id = %s AND memory_type = 'working'"
                "  AND created_at < %s ORDER BY created_at LIMIT %s"
                ")",
                (org_a, org_a, cutoff, batch),
            )
            if cur.rowcount < batch:
                break

        cur.execute(
            "SELECT memory_type, scope, content FROM public.ai_memories "
            "WHERE organization_id = %s ORDER BY content",
            (org_a,),
        )
        assert cur.fetchall() == [
            ("long_term", "manual", "durable row"),
            ("working", "research", "fresh row"),
        ]
        cur.execute(
            "SELECT count(*) FROM public.ai_memories "
            "WHERE organization_id = %s AND content = 'expired row'",
            (org_b,),
        )
        assert cur.fetchone()[0] == 1
    migrated_db.commit()


def test_rls_org_isolation_ai_memories_knowledge(migrated_db) -> None:
    """RLS org isolation works for the tables the M4 ops touch.

    Applies the repo's policy files verbatim (ai_memories + knowledge_items)
    and models the Supabase Auth runtime: ``auth.uid()`` resolves from
    ``request.jwt.claims.sub`` and ``tenant_org_id()`` runs as the table owner
    (SECURITY DEFINER), which is how the Supabase-managed environment executes
    it. Each authenticated user sees/edits only its own org's rows.
    """
    _insert_org(migrated_db, ORG_ID)
    org_b = str(uuid.uuid4())
    _insert_org(migrated_db, org_b)

    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (ORG_ID, "owner-a@example.com", "Owner A", "owner"),
        )
        user_a = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (org_b, "owner-b@example.com", "Owner B", "owner"),
        )
        user_b = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.ai_memories (organization_id, scope, content) "
            "VALUES (%s, 'research', 'memory-a') RETURNING id",
            (ORG_ID,),
        )
        cur.fetchone()
        cur.execute(
            "INSERT INTO public.ai_memories (organization_id, scope, content) "
            "VALUES (%s, 'research', 'memory-b') RETURNING id",
            (org_b,),
        )
        mem_b = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.knowledge_items (organization_id, title, content, category) "
            "VALUES (%s, 'knowledge-a', 'content-a', 'knowledge') RETURNING id",
            (ORG_ID,),
        )
        cur.fetchone()
        cur.execute(
            "INSERT INTO public.knowledge_items (organization_id, title, content, category) "
            "VALUES (%s, 'knowledge-b', 'content-b', 'knowledge') RETURNING id",
            (org_b,),
        )
        knowledge_b = cur.fetchone()[0]
    migrated_db.commit()

    # -- Runtime modeling: auth schema, uid(), helper as owner, grants.
    with migrated_db.cursor() as cur:
        cur.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated')"
            " THEN CREATE ROLE authenticated; END IF; END $$;"
        )
        cur.execute("CREATE SCHEMA IF NOT EXISTS auth")
        cur.execute(
            "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE "
            "SECURITY DEFINER AS $$ SELECT (NULLIF(current_setting('request.jwt.claims', true), '')"
            "::jsonb ->> 'sub')::uuid $$"
        )
        cur.execute((POLICIES_DIR / "_helpers.sql").read_text(encoding="utf-8"))
        cur.execute("ALTER FUNCTION public.tenant_org_id() SECURITY DEFINER")
        cur.execute((POLICIES_DIR / "ai_memories.sql").read_text(encoding="utf-8"))
        cur.execute((POLICIES_DIR / "knowledge_items.sql").read_text(encoding="utf-8"))
        cur.execute("GRANT USAGE ON SCHEMA auth TO authenticated")
        cur.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON public.ai_memories, "
            "public.knowledge_items TO authenticated"
        )
    migrated_db.commit()

    # -- User A can see only A's rows, insert into A only, and cannot touch B.
    with migrated_db.cursor() as cur:
        cur.execute("SET ROLE authenticated")
        cur.execute("SET request.jwt.claims = %s", (f'{{"sub": "{user_a}"}}',))
        cur.execute("SELECT count(*) FROM public.ai_memories")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT content FROM public.ai_memories")
        assert cur.fetchone()[0] == "memory-a"
        cur.execute("SELECT count(*) FROM public.knowledge_items")
        assert cur.fetchone()[0] == 1
        cur.execute(
            "INSERT INTO public.ai_memories (organization_id, scope, content) "
            "VALUES (%s, 'research', 'memory-a-2') RETURNING id",
            (ORG_ID,),
        )
        assert cur.fetchone()[0] is not None
        # RLS silently filters rows of other orgs: the DELETE matches nothing.
        cur.execute("DELETE FROM public.ai_memories WHERE id = %s", (mem_b,))
        assert cur.rowcount == 0
        cur.execute("DELETE FROM public.knowledge_items WHERE id = %s", (knowledge_b,))
        assert cur.rowcount == 0
    migrated_db.commit()

    # -- User B sees only B's rows.
    with migrated_db.cursor() as cur:
        cur.execute("SET ROLE authenticated")
        cur.execute("SET request.jwt.claims = %s", (f'{{"sub": "{user_b}"}}',))
        cur.execute("SELECT content FROM public.ai_memories")
        assert cur.fetchone()[0] == "memory-b"
        cur.execute("SELECT count(*) FROM public.ai_memories")
        assert cur.fetchone()[0] == 1
    migrated_db.commit()

    # -- RLS rejects cross-org INSERT for A (policy WITH CHECK violation).
    with migrated_db.cursor() as cur:
        cur.execute("SET ROLE authenticated")
        cur.execute("SET request.jwt.claims = %s", (f'{{"sub": "{user_a}"}}',))
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO public.ai_memories (organization_id, scope, content) "
                "VALUES (%s, 'research', 'sneaky')",
                (org_b,),
            )
    migrated_db.rollback()
    with migrated_db.cursor() as cur:
        cur.execute("SET ROLE authenticated")
        cur.execute("SET request.jwt.claims = %s", (f'{{"sub": "{user_a}"}}',))
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO public.knowledge_items "
                "(organization_id, title, content, category) "
                "VALUES (%s, 'sneaky', 'x', 'knowledge')",
                (org_b,),
            )
        migrated_db.rollback()
        cur.execute("RESET ROLE")
    migrated_db.commit()

    # -- The A rows (incl. the extra insert) survived; B's are untouched.
    with migrated_db.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.ai_memories WHERE organization_id = %s", (ORG_ID,))
        assert cur.fetchone()[0] == 2
        cur.execute(
            "SELECT count(*) FROM public.knowledge_items WHERE organization_id = %s",
            (org_b,),
        )
        assert cur.fetchone()[0] == 1


def test_rls_org_isolation_leads_conversations(migrated_db) -> None:
    """RLS org isolation holds for the lead + conversation tenant data too.

    M10 extends the M4 isolation proof to the core CRM tables. Applies the
    repo's ``leads.sql`` + ``conversations.sql`` policies verbatim and models
    the Supabase Auth runtime exactly like ``test_rls_org_isolation_...``:
    each authenticated user sees/edits only its own org's rows, and a
    cross-org INSERT is rejected by the WITH CHECK policy.
    """
    _insert_org(migrated_db, ORG_ID)
    org_b = str(uuid.uuid4())
    _insert_org(migrated_db, org_b)

    with migrated_db.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (ORG_ID, "owner-a@example.com", "Owner A", "owner"),
        )
        user_a = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (org_b, "owner-b@example.com", "Owner B", "owner"),
        )
        user_b = cur.fetchone()[0]
        # A lead + an open conversation for org A (conversation needs a lead).
        cur.execute(
            "INSERT INTO public.leads (organization_id, first_name) "
            "VALUES (%s, 'lead-a') RETURNING id",
            (ORG_ID,),
        )
        lead_a = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.leads (organization_id, first_name) "
            "VALUES (%s, 'lead-b') RETURNING id",
            (org_b,),
        )
        lead_b = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.conversations (organization_id, lead_id, channel) "
            "VALUES (%s, %s, 'email') RETURNING id",
            (ORG_ID, lead_a),
        )
        cur.fetchone()
        cur.execute(
            "INSERT INTO public.conversations (organization_id, lead_id, channel) "
            "VALUES (%s, %s, 'email') RETURNING id",
            (org_b, lead_b),
        )
        conv_b = cur.fetchone()[0]
    migrated_db.commit()

    # -- Runtime modeling: auth schema, uid(), helper as owner, grants.
    with migrated_db.cursor() as cur:
        cur.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated')"
            " THEN CREATE ROLE authenticated; END IF; END $$;"
        )
        cur.execute("CREATE SCHEMA IF NOT EXISTS auth")
        cur.execute(
            "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE "
            "SECURITY DEFINER AS $$ SELECT (NULLIF(current_setting('request.jwt.claims', true), '')"
            "::jsonb ->> 'sub')::uuid $$"
        )
        cur.execute((POLICIES_DIR / "_helpers.sql").read_text(encoding="utf-8"))
        cur.execute("ALTER FUNCTION public.tenant_org_id() SECURITY DEFINER")
        cur.execute((POLICIES_DIR / "leads.sql").read_text(encoding="utf-8"))
        cur.execute((POLICIES_DIR / "conversations.sql").read_text(encoding="utf-8"))
        cur.execute("GRANT USAGE ON SCHEMA auth TO authenticated")
        cur.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON public.leads, "
            "public.conversations TO authenticated"
        )
    migrated_db.commit()

    # -- User A sees only A's lead + conversation.
    with migrated_db.cursor() as cur:
        cur.execute("SET ROLE authenticated")
        cur.execute("SET request.jwt.claims = %s", (f'{{"sub": "{user_a}"}}',))
        cur.execute("SELECT count(*) FROM public.leads")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT first_name FROM public.leads")
        assert cur.fetchone()[0] == "lead-a"
        cur.execute("SELECT count(*) FROM public.conversations")
        assert cur.fetchone()[0] == 1
        # RLS silently filters other orgs on DELETE.
        cur.execute("DELETE FROM public.leads WHERE id = %s", (lead_b,))
        assert cur.rowcount == 0
        cur.execute("DELETE FROM public.conversations WHERE id = %s", (conv_b,))
        assert cur.rowcount == 0
    migrated_db.commit()

    # -- User B sees only B's lead + conversation.
    with migrated_db.cursor() as cur:
        cur.execute("SET ROLE authenticated")
        cur.execute("SET request.jwt.claims = %s", (f'{{"sub": "{user_b}"}}',))
        cur.execute("SELECT first_name FROM public.leads")
        assert cur.fetchone()[0] == "lead-b"
        cur.execute("SELECT count(*) FROM public.leads")
        assert cur.fetchone()[0] == 1
    migrated_db.commit()

    # -- RLS rejects cross-org INSERT for A (WITH CHECK violation).
    with migrated_db.cursor() as cur:
        cur.execute("SET ROLE authenticated")
        cur.execute("SET request.jwt.claims = %s", (f'{{"sub": "{user_a}"}}',))
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO public.leads (organization_id, first_name) VALUES (%s, 'sneaky')",
                (org_b,),
            )
        migrated_db.rollback()
        # The rollback above also reverts the transaction-scoped
        # ``SET request.jwt.claims`` to user_b (from the previous block), so the
        # auth context must be re-asserted before the next cross-org attempt.
        cur.execute("SET ROLE authenticated")
        cur.execute("SET request.jwt.claims = %s", (f'{{"sub": "{user_a}"}}',))
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO public.conversations (organization_id, lead_id, channel) "
                "VALUES (%s, %s, 'whatsapp')",
                (org_b, lead_b),
            )
        migrated_db.rollback()
        cur.execute("RESET ROLE")
    migrated_db.commit()


def test_migration_0027_m9_intelligence_signals(migrated_db) -> None:
    """0027 adds the M9 signal feed: enums, table, dedup + trigger + checks."""
    org_id = str(uuid.uuid4())
    _insert_org(migrated_db, org_id)
    with migrated_db.cursor() as cur:
        # Defaults: severity info, confidence low, status active, score 0.
        cur.execute(
            "INSERT INTO public.intelligence_signals "
            "(organization_id, signal_category, source_type, title, summary, "
            " content_hash) "
            "VALUES (%s, 'business_insight', 'business_insight', 'Title', "
            " 'Summary text', 'hash-1') RETURNING id, status, severity, "
            " confidence, priority_score",
            (org_id,),
        )
        signal_id, status, severity, confidence, priority_score = cur.fetchone()
        assert (status, severity, confidence) == ("active", "info", "low")
        assert float(priority_score) == 0.0

        # updated_at trigger fires on write.
        cur.execute(
            "UPDATE public.intelligence_signals SET title = 'Title 2' WHERE id = %s",
            (signal_id,),
        )
        cur.execute(
            "SELECT length(btrim(title)) > 0 FROM public.intelligence_signals WHERE id = %s",
            (signal_id,),
        )
        assert cur.fetchone()[0] is True

        # Live dup on the same content_hash -> unique violation.
        with pytest.raises(errors.UniqueViolation):
            cur.execute(
                "INSERT INTO public.intelligence_signals "
                "(organization_id, signal_category, source_type, title, summary, "
                " content_hash) "
                "VALUES (%s, 'business_insight', 'business_insight', 'Title 3', "
                " 'Summary text', 'hash-1')",
                (org_id,),
            )
    migrated_db.rollback()

    with migrated_db.cursor() as cur:
        # Supersede frees the hash for a re-emission.
        cur.execute(
            "UPDATE public.intelligence_signals SET status = 'superseded' "
            "WHERE organization_id = %s AND content_hash = 'hash-1'",
            (org_id,),
        )
        cur.execute(
            "INSERT INTO public.intelligence_signals "
            "(organization_id, signal_category, source_type, title, summary, "
            " content_hash) "
            "VALUES (%s, 'business_insight', 'business_insight', 'Title 3', "
            " 'Summary text', 'hash-1') RETURNING id",
            (org_id,),
        )
        assert cur.fetchone()[0] is not None

        # priority_score must stay in [0, 1].
        with pytest.raises(errors.CheckViolation):
            cur.execute(
                "INSERT INTO public.intelligence_signals "
                "(organization_id, signal_category, source_type, title, summary, "
                " content_hash, priority_score) "
                "VALUES (%s, 'pipeline_risk', 'pipeline_fact', 'Bad', 'Bad', "
                " 'hash-2', 1.5)",
                (org_id,),
            )
        migrated_db.rollback()
        # Blank title/summary/hash rejected by the CHECK constraints.
        with pytest.raises(errors.CheckViolation):
            cur.execute(
                "INSERT INTO public.intelligence_signals "
                "(organization_id, signal_category, source_type, title, summary, "
                " content_hash) "
                "VALUES (%s, 'pipeline_risk', 'pipeline_fact', '   ', 'ok', 'hash-3')",
                (org_id,),
            )
        migrated_db.rollback()
        with pytest.raises(errors.CheckViolation):
            cur.execute(
                "INSERT INTO public.intelligence_signals "
                "(organization_id, signal_category, source_type, title, summary, "
                " content_hash) "
                "VALUES (%s, 'pipeline_risk', 'pipeline_fact', 'ok', 'ok', '   ')",
                (org_id,),
            )
        migrated_db.rollback()
        # Enum values are enforced.
        with pytest.raises(errors.InvalidTextRepresentation):
            cur.execute(
                "INSERT INTO public.intelligence_signals "
                "(organization_id, signal_category, source_type, title, summary, "
                " content_hash) "
                "VALUES (%s, 'not_a_category', 'pipeline_fact', 'ok', 'ok', 'hash-4')",
                (org_id,),
            )
    migrated_db.rollback()


def _enum_column(model, attr):
    col = model.__table__.c[attr]
    enum_type = col.type
    assert enum_type.__class__.__name__ == "Enum", (model, attr, enum_type)
    return enum_type


def test_user_role_enum_binds_by_value_not_name() -> None:
    # Regression for BASELINE-DB-004: SQLAlchemy must bind/read the user_role
    # column by the Python enum VALUE (lowercase, e.g. "owner") which matches the
    # Postgres enum labels, NOT by the member NAME (uppercase, e.g. "OWNER")
    # which the DB rejects. If the values_callable fix is removed, this fails
    # loudly (both locally and in CI) instead of only surfacing as 34 broken
    # ORM inserts at runtime.
    role_col = _enum_column(User, "role")
    assert role_col.values_callable is not None, "user_role Enum missing values_callable"
    bound = set(role_col.values_callable(UserRole))
    assert bound == {m.value for m in UserRole}, bound
    # The drift condition: no bound value may equal a member NAME (uppercase).
    assert bound.isdisjoint({m.name for m in UserRole}), bound

    invite_role_col = _enum_column(TeamInvite, "role")
    assert invite_role_col.values_callable is not None
    assert set(invite_role_col.values_callable(UserRole)) == {m.value for m in UserRole}

    invite_status_col = _enum_column(TeamInvite, "status")
    assert invite_status_col.values_callable is not None
    assert set(invite_status_col.values_callable(InviteStatus)) == {m.value for m in InviteStatus}


def test_user_role_pg_enum_labels_match_python_values(migrated_db) -> None:
    # Regression for BASELINE-DB-004: the Postgres user_role enum labels must
    # equal the Python UserRole values (the contract the values_callable fix
    # relies on). A mismatch here is the root cause of the "invalid input value
    # for enum user_role: OWNER" failure.
    with migrated_db.cursor() as cur:
        cur.execute(
            "SELECT e.enumlabel FROM pg_type t "
            "JOIN pg_enum e ON e.enumtypid = t.oid "
            "WHERE t.typname = 'user_role'"
        )
        labels = {row[0] for row in cur.fetchall()}
    assert labels == {m.value for m in UserRole}, labels
    # Sanity: labels are lowercase values, never uppercase member names.
    assert labels == {"owner", "admin", "manager", "member", "sales_agent", "viewer"}


def test_datetime_columns_timezone_aware() -> None:
    # Regression for BASELINE-DB-005: timestamp columns of the auth/approval/
    # team-invite flows must be declared timezone-aware (DateTime(timezone=True))
    # so SQLAlchemy reads the timestamptz column back as an aware UTC datetime.
    # A naive declaration makes reads naive and triggers
    #   asyncpg.exceptions.DataError: can't subtract offset-naive and offset-aware
    # datetimes
    # on lifetime arithmetic (e.g. team_service `invite.expires_at <= utcnow()`
    # and approval_service `now > request.expires_at`). This is the canonical
    # convention used by every other timestamp column (TimestampMixin).
    expected = {
        RefreshToken: ("expires_at", "created_at", "revoked_at"),
        ApprovalRequest: ("expires_at", "decided_at", "gate_handled_at"),
        TeamInvite: ("expires_at", "accepted_at", "revoked_at"),
    }
    for model, col_names in expected.items():
        for col_name in col_names:
            col_type = model.__table__.c[col_name].type
            assert isinstance(col_type, DateTime), (
                f"{model.__name__}.{col_name} is not DateTime: {col_type!r}"
            )
            assert col_type.timezone is True, (
                f"{model.__name__}.{col_name} must be timezone-aware; got {col_type!r}"
            )
