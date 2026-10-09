"""Per-request tenant context (PostgreSQL GUC propagation).

The backend database layer runs against rows that are optionally protected by
Row Level Security. When the connection role is subject to RLS the policies
scope every row by ``organization_id = public.tenant_org_id()``, and
``tenant_org_id()`` reads a session GUC ``app.current_organization_id`` (see
``database/migrations/0033_tenant_isolation_rls.sql``).

This module owns the single source of truth for "which organization is the
current request acting on":

* ``activate_org(session, org_id)`` stamps the active organization on an
  :class:`~sqlalchemy.ext.asyncio.AsyncSession` and records it in a
  :class:`contextvars.ContextVar`.

``app/core/database.py`` attaches a transaction-begin listener that re-applies
the GUC from the ContextVar on every new transaction. That guarantees a pooled
connection can never carry one request's organization into another request's
transaction, even after a mid-request COMMIT, while the ``set_config`` call
here makes the value visible immediately to the current transaction.

In non-RLS environments (dev/CI connected as the table owner), the GUC is
harmless and purely advisory.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# The session-local PostgreSQL GUC read by tenant_org_id() in the RLS policies.
ORG_GUC_NAME = "app.current_organization_id"

# Per-task organization context. The database begin-listener reads it; the
# routing code sets it before any user-scoped work touches the database.
_current_organization_id: ContextVar[uuid.UUID | None] = ContextVar(
    "agencyos_current_organization_id", default=None
)

# Stand-in value stored when the current organization is unset. ``set_config``
# needs a non-NULL value, and the RLS helper treats '' as "no tenant".
_UNSET_ORG = ""


def get_current_organization_id() -> uuid.UUID | None:
    """Return the organization id active for the current async task."""
    return _current_organization_id.get()


def set_current_organization_id(organization_id: uuid.UUID | None) -> None:
    """Record the active organization for the current async task only."""
    _current_organization_id.set(organization_id)


async def activate_org(session: AsyncSession, organization_id: uuid.UUID | None) -> None:
    """Make ``organization_id`` the active tenant for ``session``.

    The ContextVar drives the transaction-begin listener so every later
    transaction on this connection is scoped to the organization. The direct
    ``set_config`` guarantees RLS policies see the value immediately, even if
    the current transaction began before this call.
    """
    set_current_organization_id(organization_id)
    if organization_id is None:
        await session.execute(
            text("SELECT set_config(:name, '', false)"), {"name": ORG_GUC_NAME}
        )
        return
    await session.execute(
        text("SELECT set_config(:name, :value, false)"),
        {"name": ORG_GUC_NAME, "value": str(organization_id)},
    )


async def deactivate_org(session: AsyncSession) -> None:
    """Clear the active tenant from the session and the current task context."""
    await activate_org(session, None)