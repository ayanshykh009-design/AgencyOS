"""Test-only PostgreSQL connection helpers.

Kept out of application code on purpose. These helpers let integration/e2e
fixtures open a per-test database while PRESERVING the original credentials.

NOTE: ``psycopg2.connection.get_dsn_parameters()`` intentionally strips the
password from the returned dict. Cloning an admin connection through it and
passing the result to ``psycopg2.connect(**params)`` therefore opens the
per-test database WITHOUT a password (``fe_sendauth: no password supplied``).
Always swap only the database name on the original authenticated DSN instead.
"""
from urllib.parse import urlparse, urlunparse

import psycopg2
from psycopg2 import sql as _sql

# Supabase compatibility roles referenced by the application schema (migrations
# and RLS policies). A plain PostgreSQL environment does not provision them.
COMPAT_ROLES = ("anon", "authenticated")


def dsn_for_database(url: str, dbname: str) -> str:
    """Return ``url`` with only the database (path) component replaced.

    The scheme, credentials, host, and port are preserved verbatim, so the
    resulting connection still authenticates with the password carried by
    ``url``. This is the safe alternative to ``get_dsn_parameters()`` for
    cloning a connection to a different database on the same server.
    """
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{dbname}"))


def ensure_compat_roles(admin_dsn: str) -> None:
    """Create the Supabase compatibility roles required by the schema.

    The application schema (migrations + RLS policies) references the Supabase
    ``anon`` and ``authenticated`` roles -- e.g. ``REVOKE ... FROM anon,
    authenticated`` in ``0007_auth.sql`` and ``FOR ... TO authenticated``
    policies. A plain PostgreSQL environment (such as the CI service) does not
    provision these roles, so they must be created once at the cluster level
    before migrations run. Roles are cluster-global, so creating them on the
    admin connection makes them visible to every disposable test database.

    This is a test/CI-only compatibility shim. It does NOT alter production
    semantics, weaken RLS, grant elevated privileges (the roles are ``NOLOGIN``
    with no grants), or enable trust authentication. The roles carry no
    privileges of their own; tests that need them grant exactly what they
    require (e.g. ``GRANT ... TO authenticated``) themselves.
    """
    with psycopg2.connect(admin_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for role in COMPAT_ROLES:
                cur.execute(
                    _sql.SQL("CREATE ROLE IF NOT EXISTS {} NOLOGIN").format(
                        _sql.Identifier(role)
                    )
                )
