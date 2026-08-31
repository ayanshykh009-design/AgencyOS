"""Founder action worker: expires stale founder proposals.

Sweeps PROPOSED founder proposals whose ``expires_at`` has passed and transitions
them (and their linked approval requests) to EXPIRED. Runs as a standalone loop
(``python -m app.workers.founder_action_worker``).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.metrics import get_counter
from app.core.observability import span
from app.services.founder_action_service import FounderActionService
from app.services.monitoring_service import WorkerHealthService

logger = logging.getLogger("agencyos.founder.action")

INSTANCE_ID = uuid.uuid4()
_WORKER_TYPE = "founder_action"


class FounderActionWorker:
    """Expires stale founder action proposals."""

    def __init__(self, session_factory=async_session_factory) -> None:
        self._session_factory = session_factory

    async def heartbeat(
        self, *, loop_ok: bool, last_error: str | None, counters: dict | None = None
    ) -> None:
        """Upsert this instance's heartbeat row. Best-effort: a heartbeat
        failure must never take down the worker loop."""
        try:
            async with self._session_factory() as session:
                svc = WorkerHealthService(session)
                await svc.heartbeat(
                    worker_type=_WORKER_TYPE,
                    instance_id=INSTANCE_ID,
                    loop_ok=loop_ok,
                    last_error=last_error,
                    counters=counters or {},
                )
                await session.commit()
        except Exception:  # noqa: BLE001 - heartbeat must never kill the loop
            logger.exception("founder action worker heartbeat failed")

    async def sweep_once(self) -> dict[str, int]:
        counters = {"expired": 0}
        async with self._session_factory() as session:
            expired = await FounderActionService(session).expire_due_all()
            counters["expired"] = expired
            if expired:
                get_counter(
                    "founder_proposals_expired_total",
                    description="Founder proposals auto-expired by the sweep",
                ).add(expired)
        return counters

    async def run_loop(self) -> None:
        if not settings.FOUNDER_ASSISTANT_ENABLED:
            logger.info("FOUNDER_ASSISTANT_ENABLED=false; founder action worker will not run")
            return
        logger.info("founder action worker starting (instance=%s)", INSTANCE_ID)
        while True:
            loop_start = asyncio.get_event_loop().time()
            loop_ok = True
            last_error: str | None = None
            counters: dict = {}
            try:
                await self.heartbeat(loop_ok=True, last_error=None, counters={})
                with span("founder_action_worker.sweep"):
                    counters = await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                loop_ok = False
                last_error = str(exc)
                logger.exception("founder action worker loop error")
            finally:
                await self.heartbeat(
                    loop_ok=loop_ok, last_error=last_error, counters=counters
                )

            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_s = max(1, settings.DELIVERY_POLL_INTERVAL_SECONDS - elapsed)
            try:
                await asyncio.sleep(sleep_s)
            except asyncio.CancelledError:
                raise

    async def run_once(self) -> dict[str, int]:
        """Single sweep (used by tests / schedulers)."""
        return await self.sweep_once()


def _worker_entrypoint() -> None:
    asyncio.run(FounderActionWorker().run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
