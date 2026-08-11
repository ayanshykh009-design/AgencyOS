"""Approval gate worker: applies terminal approval decisions to gated executions.

The worker sweeps terminal approval requests (approved/denied/expired/cancelled)
that have a linked workflow execution and whose gate has not been handled yet.

- APPROVED     -> requeue the gated execution (fresh attempt budget via retry())
- DENIED/EXPIRED/CANCELLED -> cancel the gated execution

Stamps ``gate_handled_at`` to guarantee idempotent processing.

Runs as a standalone loop (``python -m app.workers.approval_gate_worker``).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.metrics import get_counter
from app.core.observability import span
from app.services.approval_gate_service import ApprovalGateService
from app.services.monitoring_service import WorkerHealthService

logger = logging.getLogger("agencyos.communication.gate")

# Identity for this worker instance, stable across the process
INSTANCE_ID = uuid.uuid4()

_HEARTBEAT_COUNTERS = (
    "approval_gate_handled_total",
)


class ApprovalGateWorker:
    """Applies terminal approval decisions to gated workflow executions."""

    _WORKER_TYPE = "approval_gate"

    def __init__(self, session_factory=async_session_factory) -> None:
        self._session_factory = session_factory

    # -- heartbeat -------------------------------------------------------

    async def heartbeat(
        self,
        *,
        loop_ok: bool,
        last_error: str | None,
        counters: dict | None = None,
    ) -> None:
        """Upsert this instance's heartbeat row."""
        async with self._session_factory() as session:
            svc = WorkerHealthService(session)
            await svc.heartbeat(
                worker_type=self._WORKER_TYPE,
                instance_id=INSTANCE_ID,
                loop_ok=loop_ok,
                last_error=last_error,
                counters=counters or {},
            )
            await session.commit()

    # -- sweep loop ------------------------------------------------------

    async def sweep_once(self) -> dict[str, int]:
        """One full sweep of unhandled gates."""
        counters = {"handled": 0}

        async with self._session_factory() as session:
            gate_service = ApprovalGateService(session)
            handled = await gate_service.sweep(limit=50)
            counters["handled"] = handled

            if handled:
                get_counter(
                    "approval_gate_handled_total",
                    description="Approval gates applied to executions",
                ).add(handled)

        return counters

    async def run_loop(self) -> None:
        """Continuous polling loop (runs until cancelled)."""
        if not settings.DELIVERY_ENABLED:
            logger.info("DELIVERY_ENABLED=false; approval gate worker will not run")
            return

        logger.info("approval gate worker starting (instance=%s)", INSTANCE_ID)
        while True:
            loop_start = datetime.now().astimezone()
            loop_ok = True
            last_error: str | None = None
            try:
                await self.heartbeat(loop_ok=True, last_error=None, counters={})
                with span("approval_gate_worker.sweep"):
                    counters = await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                loop_ok = False
                last_error = str(exc)
                logger.exception("approval gate worker loop error")
            finally:
                await self.heartbeat(loop_ok=loop_ok, last_error=last_error, counters=counters)

            # Sleep until next poll
            elapsed = (datetime.now().astimezone() - loop_start).total_seconds()
            sleep_s = max(1, settings.DELIVERY_POLL_INTERVAL_SECONDS - elapsed)
            try:
                await asyncio.sleep(sleep_s)
            except asyncio.CancelledError:
                raise

    # Alias for CLI / single-sweep compatibility
    async def run_once(self) -> dict[str, int]:
        """Single sweep (used by tests / schedulers)."""
        return await self.sweep_once()


def _worker_entrypoint() -> None:
    """Entrypoint for ``python -m app.workers.approval_gate_worker``."""
    asyncio.run(ApprovalGateWorker().run_loop())


if __name__ == "__main__":
    _worker_entrypoint()