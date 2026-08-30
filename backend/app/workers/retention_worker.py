"""Retention worker: bounded, chunked pruning of automation telemetry.

Deletes ``execution_events`` older than ``EXECUTION_EVENT_RETENTION_DAYS`` and
``delivery_events`` older than ``DELIVERY_EVENT_RETENTION_DAYS``, and prunes
heartbeat rows for worker instances that have been gone for the same window.
The business trails are intentionally preserved:

- ``activity_logs`` (the immutable business audit trail) is never auto-deleted.
- ``workflow_executions`` (execution records) are kept by default.
- ``deliveries`` (the delivery outbox) is kept by default.

Deletes run in bounded chunks (``EXECUTION_RETENTION_BATCH`` /
``DELIVERY_RETENTION_BATCH``) inside a single session, so no long transactions
or large lock footprints. The sweep is config-gated (``EXECUTION_RETENTION_ENABLED``
/ ``DELIVERY_RETENTION_ENABLED``, both default true).

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
from app.repositories.delivery_event import DeliveryEventRepository
from app.repositories.execution_event import ExecutionEventRepository
from app.services.monitoring_service import WorkerHealthService

logger = logging.getLogger("agencyos.automation.retention_worker")


class RetentionWorker:
    """Prune old telemetry in small, idempotent chunks."""

    @staticmethod
    async def _set_statement_timeout(session: AsyncSession) -> None:
        """Bound the retention statements inside the current transaction."""
        timeout_ms = settings.EXECUTION_STATEMENT_TIMEOUT_SECONDS * 1000
        await session.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))

    @classmethod
    async def _purge_execution_events(cls, session: AsyncSession, batch: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=settings.EXECUTION_EVENT_RETENTION_DAYS)
        events_repo = ExecutionEventRepository(session)
        deleted = 0
        while True:
            count = await events_repo.delete_older_than(cutoff, batch)
            deleted += count
            if count < batch:
                break
        return deleted

    @classmethod
    async def _purge_delivery_events(cls, session: AsyncSession, batch: int) -> int:
        if not settings.DELIVERY_RETENTION_ENABLED:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=settings.DELIVERY_EVENT_RETENTION_DAYS)
        events_repo = DeliveryEventRepository(session)
        deleted = 0
        while True:
            count = await events_repo.delete_older_than(cutoff, batch)
            deleted += count
            if count < batch:
                break
        return deleted

    @classmethod
    async def retention_tick(cls) -> dict[str, int]:
        """Run one retention sweep.

        Returns ``{"executions_deleted": n, "delivery_events_deleted": n, "workers_pruned": n}``.
        """
        if not settings.EXECUTION_RETENTION_ENABLED:
            return {
                "executions_deleted": 0,
                "delivery_events_deleted": 0,
                "workers_pruned": 0,
            }

        batch = settings.EXECUTION_RETENTION_BATCH
        executions_deleted = 0
        delivery_events_deleted = 0
        workers_pruned = 0

        with span("automation.retention"):
            async with async_session_factory() as session:
                await cls._set_statement_timeout(session)
                health_service = WorkerHealthService(session)
                worker_cutoff = datetime.now(UTC) - timedelta(
                    days=settings.EXECUTION_EVENT_RETENTION_DAYS
                )

                executions_deleted = await cls._purge_execution_events(session, batch)
                delivery_events_deleted = await cls._purge_delivery_events(
                    session, settings.DELIVERY_RETENTION_BATCH
                )
                workers_pruned = await health_service.prune_dead(worker_cutoff, batch)
                await session.commit()

        total_deleted = executions_deleted + delivery_events_deleted + workers_pruned
        if total_deleted:
            get_counter(
                "retention_deleted_total",
                description="Rows deleted by the retention sweep",
            ).add(total_deleted)
            if executions_deleted:
                get_counter(
                    "retention_executions_deleted_total",
                    description="Execution events deleted by the retention sweep",
                ).add(executions_deleted)
            if delivery_events_deleted:
                get_counter(
                    "retention_delivery_events_deleted_total",
                    description="Delivery events deleted by the retention sweep",
                ).add(delivery_events_deleted)
            if workers_pruned:
                get_counter(
                    "retention_workers_pruned_total",
                    description="Worker heartbeat rows pruned by the retention sweep",
                ).add(workers_pruned)
            logger.info(
                "retention sweep: executions=%s delivery_events=%s workers=%s",
                executions_deleted,
                delivery_events_deleted,
                workers_pruned,
            )
        return {
            "executions_deleted": executions_deleted,
            "delivery_events_deleted": delivery_events_deleted,
            "workers_pruned": workers_pruned,
        }

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
