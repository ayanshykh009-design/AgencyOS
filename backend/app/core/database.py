"""Database access layer.

Two persistence paths coexist:

1. **SQLAlchemy async engine** (`engine` / `get_db`) — local dev, complex
   queries, and Alembic migrations against the local Postgres mirror.
2. **Supabase client** (`get_supabase`) — managed/edge operations where RLS
   policies must be respected.

Feature code must consume these via repositories (app/repositories/).
"""

import logging
from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from supabase import Client, create_client

from app.core.config import settings
from app.core.tenant_context import ORG_GUC_NAME, get_current_organization_id

logger = logging.getLogger("agencyos")


def _build_engine(url: str) -> AsyncEngine:
    """Build an async engine with pool settings tuned for concurrent loads."""
    return create_async_engine(
        url,
        echo=settings.APP_DEBUG,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_timeout=settings.DATABASE_POOL_TIMEOUT,
        pool_pre_ping=True,
    )


def _restore_tenant_guc(conn) -> None:
    """Re-apply the current organizations's GUC for a newly begun transaction.

    Runs at the start of every transaction on the web engine. Without this a
    pooled connection reused for a different request would carry the previous
    request's ``app.current_organization_id`` (session-level GUCs survive
    COMMIT). Re-setting from the ContextVar on each transaction begin makes the
    value deterministic and defeats any mid-request COMMIT/ROLLBACK.
    """
    org_id = get_current_organization_id()
    value = str(org_id) if org_id is not None else ""
    # exec_driver_sql does not bind parameters — build the literal safely.
    # org ids are uuid4 strings; they can never include a single quote.
    escaped = value.replace("'", "''")
    conn.exec_driver_sql(
        f"SELECT set_config('{ORG_GUC_NAME}', '{escaped}', false)"
    )


# Local async engine (mirrors the Supabase schema in development).
# Pool settings are tuned for concurrent web workloads; adjust per capacity plan.
engine = _build_engine(settings.DATABASE_URL)
event.listen(engine.sync_engine, "begin", _restore_tenant_guc)

# Session factory used by repositories / FastAPI dependencies.
async_session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Worker engine: connects with the BYPASSRLS worker role so the cross-tenant
# workers (execution, delivery, retention, health sweep, ...) keep operating
# while the web engine is RLS-scoped. Falls back to the web engine when no
# dedicated worker URL is configured (dev / default CI).
if settings.WORKER_DATABASE_URL:
    worker_engine = _build_engine(settings.WORKER_DATABASE_URL)
else:
    worker_engine = _build_engine(settings.DATABASE_URL)

# Session factory used by standalone workers. Bound at import time like
# ``async_session_factory`` so module-level call sites read the same global
# (tests monkeypatch ``app.workers.<worker>.worker_session_factory``).
worker_session_factory = async_sessionmaker(
    bind=worker_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with async_session_factory() as session:
        yield session


async def check_database_connection() -> bool:
    """Return True if the database answers a trivial query (readiness probe)."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("database connectivity check failed")
        return False


@lru_cache
def get_supabase() -> Client:
    """Return a cached Supabase admin client (service-role key, server-side only).

    NOTE: never expose the service-role key to the frontend. Use the anon key
    + RLS policies for client-facing requests.

    TODO: currently reserved for managed/edge operations (RLS-aware writes);
    no feature code consumes this yet, so it is intentionally unused.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
