"""Fail-closed verification that runtime connections use the RLS-restricted roles.

Migration ``0033_tenant_isolation_rls.sql`` enables RLS on every tenant table but
deliberately does **not** apply ``FORCE ROW LEVEL SECURITY``, so that developer
and CI owner connections keep working unchanged. The consequence is that tenant
isolation depends entirely on *which role the application connects as*: a table
owner or superuser DSN bypasses every policy, which silently turns RLS into a
load-bearing myth while the whole behavioural test suite still passes (those
tests assume the restricted role via ``SET ROLE``).

``Settings.validate_for_production`` can only inspect the DSN *string*, so it
cannot tell ``agencyos_api`` from the cluster owner. This module closes that gap
by asking the database itself, at startup, whether the runtime role is actually
subject to the policies.

Expected production wiring (see ``docs/database.md`` — Row Level Security):

* ``DATABASE_URL``        -> a LOGIN role that is a member of ``agencyos_app``
* ``WORKER_DATABASE_URL`` -> a LOGIN role that is a member of ``agencyos_worker``

Workers are ``BYPASSRLS`` by design (they run cross-tenant), so the worker DSN
is checked for group membership only, never for RLS subjection.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger("agencyos.db_roles")

APP_ROLE = "agencyos_app"
WORKER_ROLE = "agencyos_worker"

# Single round-trip: who am I, am I a superuser, and which groups do I inherit?
_ROLE_SQL = text(
    """
    SELECT r.rolname,
           r.rolsuper,
           pg_has_role(r.rolname, :app_role, 'MEMBER')    AS app_member,
           pg_has_role(r.rolname, :worker_role, 'MEMBER') AS worker_member
      FROM pg_roles r
     WHERE r.rolname = current_user
    """
)


def evaluate_role(
    *,
    rolname: str | None,
    rolsuper: bool,
    app_member: bool,
    worker_member: bool,
    dsn_label: str,
    require_group: str,
) -> str | None:
    """Return an error message when the role would not honour RLS, else ``None``.

    Pure and side-effect free so the policy can be unit-tested without a
    database. ``require_group`` is the cluster group the connection must inherit
    for its policies to apply (``agencyos_app`` for API traffic,
    ``agencyos_worker`` for workers).
    """
    if not rolname:
        return f"{dsn_label}: could not resolve the current database role"
    if rolsuper:
        return (
            f"{dsn_label}: role '{rolname}' is a SUPERUSER, which bypasses row "
            f"level security entirely. Connect as a LOGIN role that is a member "
            f"of '{require_group}' instead (see docs/database.md — Row Level "
            f"Security)."
        )
    if require_group == APP_ROLE and not app_member:
        return (
            f"{dsn_label}: role '{rolname}' is not a member of '{APP_ROLE}', so "
            f"the tenant RLS policies do not apply to it. Grant membership with "
            f"'GRANT {APP_ROLE} TO {rolname};'."
        )
    if require_group == WORKER_ROLE and not worker_member:
        return (
            f"{dsn_label}: role '{rolname}' is not a member of "
            f"'{WORKER_ROLE}'. Grant membership with "
            f"'GRANT {WORKER_ROLE} TO {rolname};'."
        )
    return None


def _name(info: dict[str, object]) -> str | None:
    """Normalise the resolved role name, or ``None`` when unresolvable."""
    return str(info["rolname"]) if info.get("rolname") else None


async def _probe(conn) -> dict[str, object]:
    """Fetch the current role's attributes over an existing connection."""
    row = (
        (await conn.execute(_ROLE_SQL, {"app_role": APP_ROLE, "worker_role": WORKER_ROLE}))
        .mappings()
        .first()
    )
    if row is None:  # pragma: no cover - current_user always resolves
        return {"rolname": None, "rolsuper": False, "app_member": False, "worker_member": False}
    return dict(row)


async def verify_runtime_database_roles() -> None:
    """Refuse to boot in production when a DSN would bypass RLS.

    No-op outside production so developer/CI owner connections keep working —
    the same trade-off migration 0033 documents.
    """
    if settings.APP_ENV != "production":
        return

    # Imported lazily: app.core.database builds engines from settings at import
    # time, and this module is imported by app.main during startup.
    from app.core.database import engine, worker_engine

    async with engine.connect() as conn:
        info = await _probe(conn)
    async with worker_engine.connect() as conn:
        worker_info = await _probe(conn)

    api_err = evaluate_role(
        rolname=_name(info),
        rolsuper=bool(info["rolsuper"]),
        app_member=bool(info["app_member"]),
        worker_member=bool(info["worker_member"]),
        dsn_label="DATABASE_URL",
        require_group=APP_ROLE,
    )
    worker_err = evaluate_role(
        rolname=_name(worker_info),
        rolsuper=bool(worker_info["rolsuper"]),
        app_member=bool(worker_info["app_member"]),
        worker_member=bool(worker_info["worker_member"]),
        dsn_label="WORKER_DATABASE_URL",
        require_group=WORKER_ROLE,
    )

    problems = [err for err in (api_err, worker_err) if err]
    if problems:
        raise RuntimeError(" | ".join(problems))

    logger.info(
        "db_roles.verified api_role=%s worker_role=%s", info["rolname"], worker_info["rolname"]
    )
