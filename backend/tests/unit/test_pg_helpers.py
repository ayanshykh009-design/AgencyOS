"""Unit tests for the test-only Postgres DSN helper.

These run WITHOUT a live database. They assert the security-critical
invariant that ``dsn_for_database`` preserves the original password while
only swapping the database name — the exact property that was broken when
fixtures cloned the admin connection through ``get_dsn_parameters()``
(BASELINE-DB-001: ``fe_sendauth: no password supplied``).
"""
from urllib.parse import urlparse

from _pg_helpers import dsn_for_database


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
