"""Agent worker: drains the agent run queue through the runtime.

The worker sweeps the global agent run queue on a polling loop:

- drains QUEUED runs fairly across organizations through :class:`AgentRuntime`
  (the runtime claims each run, executes it under the hard
  ``AGENT_RUN_TIMEOUT_SECONDS`` budget, and lands a terminal state via guarded
  transitions);
- applies in-flight cancellations (RUNNING runs flagged by the cancel
  endpoint);
- re-converges stale RUNNING runs that exceeded the time budget.

It owns a session per phase and is safe to run on multiple instances: every
state transition is a guarded single-statement ``UPDATE ... RETURNING`` so only
one worker claims a run and only one lands a terminal state. Draining is
at-least-once -- a crash mid-execution leaves the row RUNNING and the stale
sweep re-converges it on the next pass.

When ``AGENT_RUNTIME_ENABLED`` is false (the deployment kill switch) the worker
is a strict no-op: no phase touches any state, so the run queue simply
accumulates until the runtime is enabled.

Runs as a standalone loop (``python -m app.workers.agent_worker``) or as a
single sweep from a scheduler.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.agents.runtime import AgentRuntime
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.errors import AppError
from app.core.metrics import get_counter, get_histogram, read_counter
from app.core.observability import span
from app.services.agent_service import AgentService
from app.services.monitoring_service import WorkerHealthService

logger = logging.getLogger("agencyos.agent.worker")

# Identity for this worker instance, stable across the process lifetime so the
# heartbeat upsert always targets one row per (worker_type, instance_id).
_WORKER_TYPE = "agent"
_INSTANCE_ID = uuid.uuid4()

_HEARTBEAT_COUNTERS = (
    "agent_run_queued_total",
    "agent_run_succeeded_total",
    "agent_run_failed_total",
    "agent_run_cancelled_total",
)

_STUCK_RUN_ERROR = "Agent run exceeded its time budget"


class AgentWorker:
    """Sweep the agent run queue through the runtime."""

    @staticmethod
    def _observe_phase(phase: str, start: float) -> None:
        """Record per-phase sweep duration (in-process + OTel when enabled)."""
        get_histogram(
            "agent_worker_phase_seconds",
            description="Agent worker phase duration",
            unit="s",
        ).observe(time.perf_counter() - start, {"phase": phase})

    @classmethod
    async def heartbeat(cls, *, loop_ok: bool = True, last_error: str | None = None) -> None:
        """Upsert this instance's heartbeat row (own session, self-contained).

        Written every loop iteration and once more on shutdown. Best-effort:
        a heartbeat failure must never take down the worker loop.
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
    async def process_queued(cls, batch_size: int | None = None) -> int:
        """Run QUEUED agent runs through the runtime (fair drain).

        Candidate organizations are selected oldest-first and each org's queue
        is drained up to ``batch_size`` per sweep, so one busy org can never
        starve the rest. Each run is claimed and finalised by the runtime; a
        run already claimed elsewhere (or cancelled) is simply skipped. An
        unexpected failure outside the guarded lifecycle rolls the phase back
        and is retried on the next sweep (at-least-once semantics).
        """
        start = time.perf_counter()
        with span("agent.worker.queued"):
            async with async_session_factory() as session:
                runtime = AgentRuntime()
                service = AgentService(session)
                orgs = await service.get_queued_orgs(settings.AGENT_RUN_ORGS_PER_SWEEP)
                processed = 0
                for org_id in orgs:
                    runs = await service.get_queued_for_org(
                        org_id, batch_size or settings.AGENT_RUN_BATCH_SIZE
                    )
                    for run in runs:
                        try:
                            final = await runtime.execute_run(session, run)
                        except Exception:
                            await session.rollback()
                            logger.exception(
                                "agent run %s failed outside the guarded lifecycle",
                                run.id,
                            )
                            continue
                        if final is not None:
                            processed += 1
                    await session.commit()
        get_counter(
            "agent_run_drained_total",
            description="Agent runs drained from the queue",
        ).add(processed)
        cls._observe_phase("queued", start)
        return processed

    @classmethod
    async def process_cancels(cls, limit: int | None = None) -> int:
        """Apply in-flight cancellations (RUNNING runs flagged by the API)."""
        start = time.perf_counter()
        with span("agent.worker.cancels"):
            async with async_session_factory() as session:
                service = AgentService(session)
                runs = await service.get_cancel_requested(limit or settings.AGENT_RUN_BATCH_SIZE)
                cancelled = 0
                for run in runs:
                    try:
                        await service.apply_cancel(run.organization_id, run.id)
                    except AppError:
                        logger.info(
                            "cancel already applied for run %s (state changed)",
                            run.id,
                        )
                        continue
                    cancelled += 1
                await session.commit()
        cls._observe_phase("cancels", start)
        return cancelled

    @classmethod
    async def reconcile_stuck(cls) -> int:
        """Fail RUNNING runs that exceeded the hard time budget.

        A run whose worker died mid-execution stays RUNNING; the next sweep
        re-converges it to a terminal state. ``fail_run`` honours a concurrent
        cancel flag, so a flagged stuck run lands on CANCELLED instead.
        """
        start = time.perf_counter()
        with span("agent.worker.stuck"):
            async with async_session_factory() as session:
                service = AgentService(session)
                runs = await service.get_stuck_running()
                transitioned = 0
                for run in runs:
                    try:
                        await service.fail_run(
                            run.organization_id,
                            run.id,
                            error=_STUCK_RUN_ERROR,
                        )
                    except AppError:
                        logger.info(
                            "stuck run %s already transitioned (state changed)",
                            run.id,
                        )
                        continue
                    transitioned += 1
                await session.commit()
        cls._observe_phase("stuck", start)
        return transitioned

    @classmethod
    async def sweep(cls) -> dict[str, int]:
        """Run one full pass: queued + cancels + stuck reconciliation.

        When ``AGENT_RUNTIME_ENABLED`` is false (deployment kill switch) every
        phase is skipped: no new work is dispatched and no state is touched.
        """
        if not settings.AGENT_RUNTIME_ENABLED:
            return {"processed": 0, "cancelled": 0, "stuck": 0}
        processed = await cls.process_queued()
        cancelled = await cls.process_cancels()
        stuck = await cls.reconcile_stuck()
        return {"processed": processed, "cancelled": cancelled, "stuck": stuck}

    @classmethod
    async def run_loop(cls) -> None:
        """Poll forever: the standalone worker entrypoint.

        Each phase owns its own session/transaction and runs at
        ``AGENT_RUN_POLL_INTERVAL_SECONDS``. Restart-safety relies on persisted
        DB state only, so a crash mid-sweep leaves no orphan work: RUNNING rows
        are re-converged by the stuck sweep on the next pass.
        """
        if not settings.AGENT_RUNTIME_ENABLED:
            logger.info("agent worker disabled (AGENT_RUNTIME_ENABLED=false)")
            return
        logger.info(
            "agent worker starting (poll %ss)",
            settings.AGENT_RUN_POLL_INTERVAL_SECONDS,
        )
        try:
            while True:
                loop_ok = True
                last_error: str | None = None
                try:
                    stats = await cls.sweep()
                    if any(stats.values()):
                        logger.info("agent worker sweep: %s", stats)
                except Exception:
                    loop_ok = False
                    last_error = "sweep failed"
                    logger.exception("agent worker sweep failed")
                await cls.heartbeat(loop_ok=loop_ok, last_error=last_error)
                await asyncio.sleep(settings.AGENT_RUN_POLL_INTERVAL_SECONDS)
        except (KeyboardInterrupt, SystemExit):
            await cls.heartbeat(loop_ok=False, last_error="shutdown")
            logger.info("agent worker stopped")
            raise


def _worker_entrypoint() -> None:
    """Entrypoint for ``python -m app.workers.agent_worker``."""
    asyncio.run(AgentWorker.run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
