"""Memory worker: bounded, org-scoped TTL cleanup of working memory.

Deletes ONLY expired working memories (``memory_type='working'`` older than
``MEMORY_WORKING_TTL_DAYS``) in bounded, idempotent, org-scoped batches:

- each tick enumerates organizations that hold expired working rows,
- for each org, ``list_expired_working`` fetches at most
  ``MEMORY_CLEANUP_BATCH_SIZE`` oldest rows and ``delete_many`` removes exactly
  those ids (org-scoped by construction), repeating until the batch drains,
- the transaction commits once per tick and the whole sweep runs inside a
  statement-timeout guard, so no long transactions or lock footprints.

Long-term memory is never eligible (the SQL predicates on ``memory_type`` and
the repository guarantees it). Promotion is deliberately NOT performed here —
promotion is a service-level concern with no worker trigger. The sweep is
config-gated (``MEMORY_CLEANUP_ENABLED``, default true).

Runs as a standalone loop (``python -m app.workers.memory_worker``). Heartbeat
semantics mirror the execution worker: best-effort, own session, never fatal.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.metrics import get_counter, get_histogram, read_counter
from app.core.observability import span
from app.models.ai_memory import AiMemory
from app.models.enums import MemoryType
from app.repositories.ai_memory import AiMemoryRepository
from app.services.monitoring_service import WorkerHealthService

logger = logging.getLogger("agencyos.automation.memory_worker")

# Identity for this worker instance, stable across the process lifetime so the
# heartbeat upsert always targets one row per (worker_type, instance_id).
_WORKER_TYPE = "memory"
_INSTANCE_ID = uuid.uuid4()

_HEARTBEAT_COUNTERS = ("agencyos.memory.cleanup.expired_total",)

# Bounds the org enumeration per tick; the sweep is idempotent so the next tick
# simply continues with any remaining orgs.
_MAX_ORGS_PER_TICK = 1000


class MemoryWorker:
    """Prune expired working memories in small, org-scoped batches."""

    @staticmethod
    async def _set_statement_timeout(session: AsyncSession) -> None:
        """Bound the cleanup statements inside the current transaction."""
        await session.execute(
            text("SET LOCAL statement_timeout = :ms"),
            {"ms": settings.EXECUTION_STATEMENT_TIMEOUT_SECONDS * 1000},
        )

    @staticmethod
    def _observe_duration(start: float) -> None:
        """Record the tick duration (in-process + OTel when enabled)."""
        get_histogram(
            "agencyos.memory.cleanup.duration_seconds",
            description="Memory cleanup worker tick duration",
            unit="s",
        ).observe(time.perf_counter() - start)

    @classmethod
    async def heartbeat(
        cls, *, loop_ok: bool = True, last_error: str | None = None
    ) -> None:
        """Upsert this instance's heartbeat row (own session, self-contained).

        Best-effort: a heartbeat failure must never take down the worker loop.
        """
        try:
            async with async_session_factory() as session:
                service = WorkerHealthService(session)
                await service.heartbeat(
                    worker_type=_WORKER_TYPE,
                    instance_id=_INSTANCE_ID,
                    loop_ok=loop_ok,
                    last_error=last_error,
                    counters={name: read_counter(name) for name in _HEARTBEAT_COUNTERS},
                )
                await session.commit()
        except Exception:
            logger.exception("worker heartbeat failed")

    @classmethod
    async def _orgs_with_expired_working(
        cls, session: AsyncSession, before: datetime
    ) -> list[uuid.UUID]:
        """Organizations that hold at least one expired working memory."""
        stmt = (
            select(AiMemory.organization_id)
            .where(
                AiMemory.memory_type == MemoryType.WORKING,
                AiMemory.created_at < before,
            )
            .distinct()
            .limit(_MAX_ORGS_PER_TICK)
        )
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]

    @classmethod
    async def cleanup_tick(cls) -> dict[str, int]:
        """Run one cleanup sweep. Returns ``{"orgs_swept": n, "expired_deleted": n}``."""
        if not settings.MEMORY_CLEANUP_ENABLED:
            return {"orgs_swept": 0, "expired_deleted": 0}

        start = time.perf_counter()
        cutoff = datetime.now(UTC) - timedelta(days=settings.MEMORY_WORKING_TTL_DAYS)
        batch = max(settings.MEMORY_CLEANUP_BATCH_SIZE, 1)
        orgs_swept = 0
        expired_deleted = 0

        with span("memory.cleanup"):
            async with async_session_factory() as session:
                await cls._set_statement_timeout(session)
                repo = AiMemoryRepository(session)

                for org_id in await cls._orgs_with_expired_working(session, cutoff):
                    orgs_swept += 1
                    while True:
                        expired = await repo.list_expired_working(
                            org_id, before=cutoff, batch=batch
                        )
                        if not expired:
                            break
                        deleted = await repo.delete_many(
                            org_id, [memory.id for memory in expired]
                        )
                        expired_deleted += deleted
                        if deleted < batch:
                            break
                await session.commit()

        if expired_deleted:
            get_counter(
                "agencyos.memory.cleanup.expired_total",
                description="Expired working memories deleted by the memory cleanup worker",
            ).add(expired_deleted)
            logger.info(
                "memory cleanup: orgs_swept=%s expired_deleted=%s",
                orgs_swept,
                expired_deleted,
            )
        cls._observe_duration(start)
        return {"orgs_swept": orgs_swept, "expired_deleted": expired_deleted}

    @classmethod
    async def run_loop(cls) -> None:
        """Poll forever: the standalone memory worker entrypoint."""
        interval = settings.MEMORY_CLEANUP_INTERVAL_SECONDS
        logger.info("memory worker starting (every %ss)", interval)
        try:
            while True:
                loop_ok = True
                last_error: str | None = None
                try:
                    stats = await cls.cleanup_tick()
                    if stats["expired_deleted"]:
                        logger.info("memory cleanup sweep stats: %s", stats)
                except Exception:
                    loop_ok = False
                    last_error = "cleanup tick failed"
                    logger.exception("memory cleanup tick failed")
                await cls.heartbeat(loop_ok=loop_ok, last_error=last_error)
                await asyncio.sleep(interval)
        except (KeyboardInterrupt, SystemExit):
            await cls.heartbeat(loop_ok=False, last_error="shutdown")
            logger.info("memory worker stopped")
            raise


def _worker_entrypoint() -> None:
    """Entrypoint for ``python -m app.workers.memory_worker``."""
    asyncio.run(MemoryWorker.run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
