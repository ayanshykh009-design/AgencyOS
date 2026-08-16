"""M11 static schema assertions (no database required).

Verifies that the SQL schema and migration mirrors for M11-C declare the
``trace_id`` column on ``agent_runs`` and that the ``ai_run`` trigger value is
present. The database integration test exercises runtime persistence; this
catches schema/migration drift before any DB is spun up.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_AGENT_RUNS = REPO_ROOT / "database" / "schema" / "agent_runs.sql"
MIGRATIONS_DIR = REPO_ROOT / "database" / "migrations"
MIGRATION_0028 = MIGRATIONS_DIR / "0028_m11_ai_run_trace.sql"


def test_agent_runs_schema_declares_trace_id() -> None:
    text = SCHEMA_AGENT_RUNS.read_text(encoding="utf-8")
    assert "trace_id" in text, "agent_runs.sql must declare trace_id (M11-C)"
    # The index from 0028 must be mirrored here too.
    assert "idx_agent_runs_trace_id" in text


def test_migration_0028_exists_and_adds_trace_id() -> None:
    assert MIGRATION_0028.exists(), "migration 0028 (M11 ai_run trace) missing"
    text = MIGRATION_0028.read_text(encoding="utf-8")
    assert "ALTER TYPE" in text and "agent_run_trigger" in text
    assert "ADD VALUE IF NOT EXISTS 'ai_run'" in text
    assert "ADD COLUMN" in text and "trace_id" in text


def test_migration_0028_registered_in_schema_sha_test() -> None:
    # test_database_schema.py pins migration SHAs; 0028 must be represented.
    sha_test_path = (
        REPO_ROOT / "backend" / "tests" / "integration" / "test_database_schema.py"
    )
    sha_test = sha_test_path.read_text(encoding="utf-8")
    assert "0028_m11_ai_run_trace.sql" in sha_test, (
        "test_database_schema.py must pin the SHA of migration 0028"
    )
