"""Unit tests for the test-only Postgres DSN helper.

These run WITHOUT a live database. They assert the security-critical
invariant that ``dsn_for_database`` preserves the original password while
only swapping the database name — the exact property that was broken when
fixtures cloned the admin connection through ``get_dsn_parameters()``
(BASELINE-DB-001: ``fe_sendauth: no password supplied``).
"""
import re
from pathlib import Path
from urllib.parse import urlparse

from _pg_helpers import COMPAT_ROLES, dsn_for_database


def test_dsn_for_database_preserves_credentials_and_swaps_db() -> None:
    url = "postgresql://agencyos:change-me@localhost:5432/agencyos"
    out = dsn_for_database(url, "agencyos_test_abc123")

    parsed = urlparse(out)
    assert parsed.scheme == "postgresql"
    assert parsed.username == "agencyos"
    assert parsed.password == "change-me"  # password MUST survive
    assert parsed.hostname == "localhost"
    assert parsed.port == 5432
    assert parsed.path == "/agencyos_test_abc123"  # only dbname changed


def test_dsn_for_database_keeps_asyncpg_scheme_and_password() -> None:
    url = "postgresql+asyncpg://agencyos:change-me@db.example.com:5432/agencyos"
    out = dsn_for_database(url, "other")

    parsed = urlparse(out)
    assert parsed.scheme == "postgresql+asyncpg"
    assert parsed.password == "change-me"
    assert parsed.hostname == "db.example.com"
    assert parsed.port == 5432
    assert parsed.path == "/other"


def test_dsn_for_database_rejects_password_loss_regression() -> None:
    # Guard against a regression where the clone would silently drop auth.
    url = "postgresql://user:s3cr3t@host:5432/db"
    out = dsn_for_database(url, "fresh")
    assert urlparse(out).password == "s3cr3t"


def test_compat_roles_match_schema_references() -> None:
    # Regression for BASELINE-DB-002: the compatibility roles bootstrapped in
    # the test/CI Postgres environment MUST exactly match the roles actually
    # referenced by the migration + RLS policy layer. If a migration or policy
    # starts referencing a new role (e.g. ``service_role``), this test fails
    # closed and forces the bootstrap contract to be updated — rather than
    # letting migrations fail at runtime with ``role "..." does not exist``.
    repo_root = Path(__file__).resolve().parents[3]
    sql_files = list((repo_root / "database" / "migrations").glob("*.sql")) + list(
        (repo_root / "database" / "supabase" / "policies").glob("*.sql")
    )
    assert sql_files, "expected schema SQL files under database/"

    role_pattern = re.compile(r"\b(anon|authenticated|service_role)\b")
    referenced: set[str] = set()
    for f in sql_files:
        for m in role_pattern.finditer(f.read_text(encoding="utf-8")):
            referenced.add(m.group(1))

    assert referenced, "expected at least one compatibility role reference"
    assert referenced == set(COMPAT_ROLES), (
        f"COMPAT_ROLES {set(COMPAT_ROLES)} must exactly match roles referenced "
        f"by migrations/RLS policies {referenced}"
    )

