"""Retention worker: bounded, chunked pruning of execution telemetry.

Deletes ``execution_events`` older than ``EXECUTION_EVENT_RETENTION_DAYS`` and
prunes heartbeat rows for worker instances that have been gone for the same
window. The business trails are intentionally preserved:

- ``activity_logs`` (the immutable business audit trail) is never auto-deleted.
- ``workflow_executions`` (execution records) are kept by default.

Deletes run in bounded chunks (``EXECUTION_RETENTION_BATCH``) inside a single
session, so no long transactions or large lock footprints. The sweep is
config-gated (``EXECUTION_RETENTION_ENABLED``, default true).

Runs as a standalone loop (``python -m app.workers.retention_worker``).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.metrics import get_counter
from app.core.observability import span
from app.repositories.execution_event import ExecutionEventRepository
from app.services.monitoring_service import WorkerHealthService

logger = logging.getLogger("agencyos.automation.retention_worker")


class RetentionWorker:
    """Prune old execution telemetry in small, idempotent chunks."""

    @staticmethod
    async def _set_statement_timeout(session: AsyncSession) -> None:
        """Bound the retention statements inside the current transaction."""
        await session.execute(
            text("SET LOCAL statement_timeout = :ms"),
            {"ms": settings.EXECUTION_STATEMENT_TIMEOUT_SECONDS * 1000},
        )

    @classmethod
    async def retention_tick(cls) -> dict[str, int]:
        """Run one retention sweep. Returns ``{"events_deleted": n, "workers_pruned": n}``."""
        if not settings.EXECUTION_RETENTION_ENABLED:
            return {"events_deleted": 0, "workers_pruned": 0}

        cutoff = datetime.now(UTC) - timedelta(
            days=settings.EXECUTION_EVENT_RETENTION_DAYS
        )
        batch = settings.EXECUTION_RETENTION_BATCH
        events_deleted = 0
        workers_pruned = 0

        with span("automation.retention"):
            async with async_session_factory() as session:
                await cls._set_statement_timeout(session)
                events_repo = ExecutionEventRepository(session)
                health_service = WorkerHealthService(session)

                while True:
                    deleted = await events_repo.delete_older_than(cutoff, batch)
                    events_deleted += deleted
                    if deleted < batch:
                        break

                pruned = await health_service.prune_dead(cutoff, batch)
                workers_pruned += pruned
                await session.commit()

        if events_deleted or workers_pruned:
            get_counter(
                "retention_deleted_total",
                description="Rows deleted by the retention sweep",
            ).add(events_deleted + workers_pruned)
            get_counter(
                "retention_executions_deleted_total",
                description="Execution events deleted by the retention sweep",
            ).add(events_deleted)
            get_counter(
                "retention_workers_pruned_total",
                description="Worker heartbeat rows pruned by the retention sweep",
            ).add(workers_pruned)
            logger.info(
                "retention sweep: events_deleted=%s workers_pruned=%s",
                events_deleted,
                workers_pruned,
            )
        return {"events_deleted": events_deleted, "workers_pruned": workers_pruned}

    @classmethod
    async def run_loop(cls) -> None:
        """Poll forever: the standalone retention worker entrypoint."""
        interval = settings.EXECUTION_RETENTION_INTERVAL_SECONDS
        logger.info("retention worker starting (every %ss)", interval)
        try:
            while True:
                try:
                    await cls.retention_tick()
                except Exception:
                    logger.exception("retention tick failed")
                await asyncio.sleep(interval)
        except (KeyboardInterrupt, SystemExit):
            logger.info("retention worker stopped")
            raise


def _worker_entrypoint() -> None:
    """Entrypoint for ``python -m app.workers.retention_worker``."""
    asyncio.run(RetentionWorker.run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
