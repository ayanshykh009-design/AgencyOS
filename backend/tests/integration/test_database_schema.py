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
POLICIES_DIR = Path(__file__).resolve().parents[3] / "database" / "supabase" / "policies"
ADMIN_URL = os.getenv(
    "TEST_POSTGRES_URL",
    settings.DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres",
)

ORG_ID = "00000000-0000-0000-0000-000000000001"

# Digest of 0018_phase5d_database_layer.sql (LF-normalized, utf-8): M4 must NOT
# modify the migration, so this pins it against accidental drift.
MIGRATION_0018_SHA256 = "78d81482401b8a74af3bc75acb36066c578a991255a31348cef9b72ae5e925bc"


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
        "schema_migrations", "workflows", "workflow_triggers",
        "workflow_executions", "workflow_events", "credentials",
        "credential_key_versions", "execution_events", "worker_health",
        "system_settings", "ai_memories", "knowledge_items", "agent_runs",
        "agent_state", "notifications", "approval_requests", "approval_logs",
        "briefings", "growth_metrics", "growth_forecasts", "business_insights",
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
    migration_0014 = (MIGRATIONS_DIR / "0014_schedule_last_fired.sql").read_text(
        encoding="utf-8"
    )
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
    migration_0017 = (MIGRATIONS_DIR / "0017_automation_hardening.sql").read_text(
        encoding="utf-8"
    )
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
            "ai_memories", "knowledge_items", "agent_runs", "agent_state",
            "notifications", "approval_requests", "approval_logs", "briefings",
            "growth_metrics", "growth_forecasts", "business_insights",
        ):
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = %s)",
                (table,),
            )
            assert cur.fetchone()[0] is True
        for enum_name in (
            "memory_type", "memory_scope", "agent_run_status", "agent_run_trigger",
            "agent_state_status", "agent_health", "notification_type",
            "approval_request_status", "approval_log_action", "briefing_type",
            "insight_type", "insight_severity", "insight_status",
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
            "AND relrowsecurity = true AND tablename IN ("
            "'ai_memories', 'knowledge_items', 'agent_runs', 'agent_state', "
            "'notifications', 'approval_requests', 'approval_logs', 'briefings', "
            "'growth_metrics', 'growth_forecasts', 'business_insights')"
        )
        assert cur.fetchone()[0] == 11

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
        cur.execute(
            "SELECT count(*) FROM public.worker_health WHERE hostname = 'dead'"
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT count(*) FROM public.worker_health WHERE hostname = 'alive'"
        )
        assert cur.fetchone()[0] == 1
    migrated_db.commit()


def test_no_migration_0019_exists() -> None:
    """M4 adds no schema migration: 0018 is the final AI-layer migration."""
    assert not list(MIGRATIONS_DIR.glob("0019_*.sql"))


def test_migration_0018_unchanged_sha256() -> None:
    """M4 must not modify 0018: the migration content is pinned by digest."""
    import hashlib

    raw = (MIGRATIONS_DIR / "0018_phase5d_database_layer.sql").read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    assert hashlib.sha256(normalized).hexdigest() == MIGRATION_0018_SHA256


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
            "'{\"category\": \"founder\"}'::jsonb, %s)",
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
        assert cur.fetchall() == [("working", "research", "fresh row"),
                                  ("long_term", "manual", "durable row")]
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
            "VALUES (%s, %s, %s, 'owner') RETURNING id",
            (ORG_ID, "owner-a@example.com"),
        )
        user_a = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.users (organization_id, email, full_name, role) "
            "VALUES (%s, %s, %s, 'owner') RETURNING id",
            (org_b, "owner-b@example.com"),
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
        cur.execute(
            (POLICIES_DIR / "_helpers.sql").read_text(encoding="utf-8")
        )
        cur.execute("ALTER FUNCTION public.tenant_org_id() SECURITY DEFINER")
        cur.execute(
            (POLICIES_DIR / "ai_memories.sql").read_text(encoding="utf-8")
        )
        cur.execute(
            (POLICIES_DIR / "knowledge_items.sql").read_text(encoding="utf-8")
        )
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
