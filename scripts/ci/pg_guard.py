#!/usr/bin/env python3
"""Fail-fast guard for `make ci` when PostgreSQL is not reachable.

Without this, `pytest` silently skips the entire integration + e2e DB layer
(a false-green `make ci`). This script mirrors the reachability probe used by
the backend integration/e2e suites and exits non-zero so `make ci` refuses to
run rather than report a green result with DB tests skipped.

Exit 0 when a PostgreSQL server is reachable, non-zero otherwise.
"""

from __future__ import annotations

import os
import sys

import psycopg2


def _admin_url() -> str:
    test_url = os.getenv("TEST_POSTGRES_URL")
    if test_url:
        return test_url
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        sys.stderr.write("pg_guard: neither TEST_POSTGRES_URL nor DATABASE_URL is set\n")
        sys.exit(1)
    # Mirror the integration suites: connect to the 'postgres' admin database.
    return db_url.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres"


def main() -> int:
    admin_url = _admin_url()
    try:
        conn = psycopg2.connect(admin_url, connect_timeout=3)
        conn.close()
    except Exception as exc:  # noqa: BLE001 - surface the concrete reason
        sys.stderr.write(f"pg_guard: PostgreSQL not reachable ({admin_url!r}): {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
