"""Intelligence triage worker (M9): sweeps orgs, materializes signals.

For each candidate org (oldest-created first, bounded per tick) the worker runs
a deterministic, idempotent sweep: collect M7/M8 output + pipeline condition
detectors, score each candidate, upsert by content hash, and supersede stale
active signals. Commits per org so a failing org never blocks the others.

Runs as a standalone loop (``python -m app.workers.intelligence_triage_worker``).
Gated on ``INTELLIGENCE_TRIAGE_ENABLED`` (fail closed when False).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.metrics import get_counter, get_histogram
from app.core.observability import span
from app.services.intelligence.intelligence_triage_service import IntelligenceTriageService
from app.services.monitoring_service import WorkerHealthService

logger = logging.getLogger("agencyos.intelligence")

INSTANCE_ID = uuid.uuid4()
_WORKER_TYPE = "intelligence_triage"


class IntelligenceTriageWorker:
    """Materializes the M9 founder intelligence signal feed."""

    def __init__(self, session_factory=async_session_factory) -> None:
        self._session_factory = session_factory

    async def heartbeat(
        self, *, loop_ok: bool, last_error: str | None, counters: dict | None = None
    ) -> None:
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

    async def sweep_once(self) -> dict[str, int]:
        totals = {"orgs": 0, "candidates": 0, "created": 0, "updated": 0, "superseded": 0}
        # Discover candidate orgs in a short-lived session...
        async with self._session_factory() as discover:
            orgs = await IntelligenceTriageService(discover).candidate_orgs()
        # ...then sweep each org in its own session so a failure in one org
        # can never leak partial writes into another org's commit.
        for org_id in orgs:
            async with self._session_factory() as session:
                try:
                    service = IntelligenceTriageService(session)
                    counters = await service.run_sweep_for_org(org_id)
                    await session.commit()
                    totals["orgs"] += 1
                    for key in ("candidates", "created", "updated", "superseded"):
                        totals[key] += counters[key]
                    get_counter(
                        "intelligence_signals_ingested_total",
                        description="Signal candidates triaged by the M9 sweep",
                    ).add(counters["candidates"])
                    get_counter(
                        "intelligence_signals_created_total",
                        description="New intelligence signals materialized",
                    ).add(counters["created"])
                    get_counter(
                        "intelligence_signals_updated_total",
                        description="Existing intelligence signals refreshed",
                    ).add(counters["updated"])
                    get_counter(
                        "intelligence_signals_superseded_total",
                        description="Active signals superseded as stale",
                    ).add(counters["superseded"])
                    get_counter(
                        "intelligence_high_priority_signals_total",
                        description="Signals scoring in the high priority band",
                    ).add(counters["high_priority"])
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - one org must not break the sweep
                    logger.exception("intelligence sweep failed for org=%s", org_id)
                    await session.rollback()
                    get_counter(
                        "intelligence_sweep_failures_total",
                        description="Intelligence sweeps that raised per org",
                    ).add(1)
                    last_error = str(exc)
                    await self.heartbeat(loop_ok=False, last_error=last_error, counters=totals)
        return totals

    async def run_loop(self) -> None:
        if not settings.INTELLIGENCE_TRIAGE_ENABLED:
            logger.info(
                "INTELLIGENCE_TRIAGE_ENABLED=false; intelligence triage worker will not run"
            )
            return
        logger.info("intelligence triage worker starting (instance=%s)", INSTANCE_ID)
        latency = get_histogram(
            "intelligence_sweep_latency_seconds",
            description="Duration of a single intelligence sweep pass",
        )
        while True:
            loop_start = asyncio.get_event_loop().time()
            loop_ok = True
            last_error: str | None = None
            counters: dict = {}
            try:
                await self.heartbeat(loop_ok=True, last_error=None, counters={})
                with span("intelligence_triage_worker.sweep"):
                    counters = await self.sweep_once()
                latency.observe(asyncio.get_event_loop().time() - loop_start)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                loop_ok = False
                last_error = str(exc)
                logger.exception("intelligence triage worker loop error")
                get_counter(
                    "intelligence_sweep_failures_total",
                    description="Intelligence sweeps that raised per org",
                ).add(1)
            finally:
                await self.heartbeat(
                    loop_ok=loop_ok, last_error=last_error, counters=counters
                )

            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_s = max(1, settings.INTELLIGENCE_TRIAGE_INTERVAL_SECONDS - elapsed)
            try:
                await asyncio.sleep(sleep_s)
            except asyncio.CancelledError:
                raise

    async def run_once(self) -> dict[str, int]:
        """Single sweep (used by tests / schedulers)."""
        return await self.sweep_once()


def _worker_entrypoint() -> None:
    asyncio.run(IntelligenceTriageWorker().run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
