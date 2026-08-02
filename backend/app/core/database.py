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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from supabase import Client, create_client

from app.core.config import settings

logger = logging.getLogger("agencyos")

# Local async engine (mirrors the Supabase schema in development).
# Pool settings are tuned for concurrent web workloads; adjust per capacity plan.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_pre_ping=True,
)

# Session factory used by repositories / FastAPI dependencies.
async_session_factory = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
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
