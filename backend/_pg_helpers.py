"""Test-only PostgreSQL connection helpers.

Kept out of application code on purpose. These helpers let integration/e2e
fixtures open a per-test database while PRESERVING the original credentials.

NOTE: ``psycopg2.connection.get_dsn_parameters()`` intentionally strips the
password from the returned dict. Cloning an admin connection through it and
passing the result to ``psycopg2.connect(**params)`` therefore opens the
per-test database WITHOUT a password (``fe_sendauth: no password supplied``).
Always swap only the database name on the original authenticated DSN instead.
"""
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg2
from psycopg2 import sql as _sql

# Supabase compatibility roles referenced by the application schema (migrations
# and RLS policies). A plain PostgreSQL environment does not provision them.
COMPAT_ROLES = ("anon", "authenticated")

# Canonical migration sources live under database/migrations. The numbered
# migrations are applied in numeric order; a few enum types (e.g. the automation
# and founder enums) are defined ONLY in database/migrations/enums/*.sql and are
# NOT created inline by any numbered migration, so they must be applied first.
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "database" / "migrations"
ENUMS_DIR = MIGRATIONS_DIR / "enums"



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

    Idempotency note: PostgreSQL does NOT support ``CREATE ROLE IF NOT EXISTS``
    (that clause exists only for CREATE TABLE/DATABASE/SCHEMA/INDEX), so the
    existence check is performed against ``pg_catalog.pg_roles`` inside a DO
    block instead. Repeated invocations are therefore safe.
    """
    with psycopg2.connect(admin_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for role in COMPAT_ROLES:
                cur.execute(
                    _sql.SQL(
                        """
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_catalog.pg_roles
                                WHERE rolname = {role}
                            ) THEN
                                CREATE ROLE {ident} NOLOGIN;
                            END IF;
                        END
                        $$;
                        """
                    ).format(role=_sql.Literal(role), ident=_sql.Identifier(role))
                )


def _inline_created_types() -> set[str]:
    """Enum types created inline by a numbered migration.

    Applying the canonical ``enums/*.sql`` file for one of these first would
    collide with the numbered migration's own (sometimes unguarded) ``CREATE
    TYPE``. Only enum files whose types are NOT in this set are applied as a
    bootstrap before the numbered migrations.

    Enums are created inline via one of three patterns:
      * ``CREATE TYPE public.<name> ...`` (guarded literal, e.g. 0017/0018/0020)
      * ``agencyos_create_enum('<name>', ARRAY[...])`` (0001 helper)
      * ``EXECUTE format('CREATE TYPE public.%I ...', '<name>', ...)`` inside a
        FOREACH loop whose array lists the type names (0008-0011)
    """
    enum_names: set[str] = set()
    for f in sorted(ENUMS_DIR.glob("*.sql")):
        etxt = f.read_text(encoding="utf-8")
        enum_names |= set(re.findall(r"CREATE TYPE public\.(\w+)", etxt, re.I))

    inline: set[str] = set()
    for nf in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        txt = nf.read_text(encoding="utf-8")
        for t in enum_names:
            if re.search(r"CREATE TYPE public\." + t + r"\b", txt, re.I):
                inline.add(t)
            elif re.search(r"agencyos_create_enum\(\s*'" + t + r"'", txt):
                inline.add(t)
            elif ("'" + t + "'" in txt) and ("CREATE TYPE public.%I" in txt):
                inline.add(t)
    return inline


def enum_bootstrap_files() -> list[Path]:
    """Canonical enum-definition files that must run before the numbered migrations.

    Mirrors the supported production order (enum bootstrap -> numbered
    migrations). A file is included only if at least one of its enum types is
    not already created inline by a numbered migration, so files whose types
    are created inline (e.g. team/assignment/task/pipeline/delivery/phase5d
    enums) are skipped to avoid ``type already exists`` collisions.
    """
    inline = _inline_created_types()
    out: list[Path] = []
    for f in sorted(ENUMS_DIR.glob("*.sql")):
        txt = f.read_text(encoding="utf-8")
        file_types = set(re.findall(r"CREATE TYPE public\.(\w+)", txt, re.I))
        if file_types and not file_types.issubset(inline):
            out.append(f)
    return out


def run_migrations(conn) -> None:
    """Apply the canonical migrations to ``conn``: enum bootstrap first, then
    the numbered migrations, each committed separately.

    Test/CI-only shim that reproduces the supported migration order
    (``scripts/db/migrate.sh`` applies the numbered migrations after the same
    enum bootstrap). ``conn`` must already have the ``schema_migrations``
    bootstrap table and the compatibility roles in place.
    """
    files = enum_bootstrap_files() + sorted(
        MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")
    )
    for path in files:
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
        conn.commit()
