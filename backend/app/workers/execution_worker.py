"""Execution worker: drains the workflow execution queue.

The worker sweeps the global execution queue on a polling loop:

- requeues due RETRYING executions,
- drains QUEUED executions through the adapter selected by the workflow's
  ``execution_mode``,
- marks stale RUNNING executions as ``timed_out``,
- dispatches due schedule triggers on its own (slower) cadence.

It owns a session per phase and is safe to run on multiple instances (state
transitions are optimistic — only one runner moves an execution out of
QUEUED/RETRYING/RUNNING, and only one runner claims a schedule tick).

Runs as a standalone loop (``python -m app.workers.execution_worker``) or as a
single sweep from a scheduler.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from functools import partial

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.errors import AppError
from app.core.metrics import get_counter, get_histogram, read_counter
from app.core.observability import span
from app.models.enums import ExecutionEventType, WorkflowStatus
from app.repositories.workflow import WorkflowRepository
from app.services.automation_control_service import AutomationControlService
from app.services.execution_adapter import adapter_error_payload, get_adapter
from app.services.monitoring_service import WorkerHealthService
from app.services.schedule_dispatcher import ScheduleDispatcher
from app.services.workflow_execution_service import WorkflowExecutionService

logger = logging.getLogger("agencyos.automation.worker")

# Identity for this worker instance, stable across the process lifetime so the
# heartbeat upsert always targets one row per (worker_type, instance_id).
_WORKER_TYPE = "execution"
_INSTANCE_ID = uuid.uuid4()

_HEARTBEAT_COUNTERS = (
    "execution_queued_total",
    "execution_drained_total",
    "execution_retried_total",
    "execution_failed_total",
    "execution_timed_out_total",
    "execution_cancelled_total",
)


class ExecutionWorker:
    """Sweep the global execution queue through the adapters."""

    @staticmethod
    async def _set_statement_timeout(session: AsyncSession) -> None:
        """Bound the phase's statements inside the current transaction."""
        await session.execute(
            text("SET LOCAL statement_timeout = :ms"),
            {"ms": settings.EXECUTION_STATEMENT_TIMEOUT_SECONDS * 1000},
        )

    @staticmethod
    def _observe_phase(phase: str, start: float) -> None:
        """Record per-phase sweep duration (in-process + OTel when enabled)."""
        get_histogram(
            "execution_worker_phase_seconds",
            description="Execution worker phase duration",
            unit="s",
        ).observe(time.perf_counter() - start, {"phase": phase})

    @classmethod
    async def heartbeat(
        cls, *, loop_ok: bool = True, last_error: str | None = None
    ) -> None:
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
    async def process_retries(cls) -> int:
        """Requeue executions whose retry window has elapsed."""
        start = time.perf_counter()
        with span("automation.worker.retries"):
            async with async_session_factory() as session:
                service = WorkflowExecutionService(session)
                await cls._set_statement_timeout(session)
                executions = await service.get_queued_for_retry()
                for execution in executions:
                    await service.retry(execution.organization_id, execution.id)
                await session.commit()
        cls._observe_phase("retries", start)
        return len(executions)

    @classmethod
    async def process_queued(cls, batch_size: int = 10) -> int:
        """Run QUEUED executions through the workflow's adapter (fair drain).

        Candidate organizations are selected oldest-first and each org's queue
        is drained up to ``batch_size`` per sweep, so one busy org can never
        starve the rest. Draining is at-least-once: a crash mid-execution
        leaves the row RUNNING and the stale sweep re-converges it
        (timeout/cancel semantics apply).
        """
        start = time.perf_counter()
        with span("automation.worker.queued"):
            async with async_session_factory() as session:
                service = WorkflowExecutionService(session)
                workflow_repo = WorkflowRepository(session)
                await cls._set_statement_timeout(session)
                orgs = await service.get_queued_orgs(settings.EXECUTION_ORGS_PER_SWEEP)
                processed = 0
                for org_id in orgs:
                    executions = await service.get_queued_for_org(org_id, batch_size)
                    if not executions:
                        continue
                    workflows = {
                        w.id: w
                        for w in await workflow_repo.get_many(
                            [e.workflow_id for e in executions]
                        )
                    }
                    for execution in executions:
                        workflow = workflows.get(execution.workflow_id)
                        if workflow is None or workflow.status != WorkflowStatus.ACTIVE:
                            try:
                                await service.fail_queued(
                                    execution.organization_id,
                                    execution.id,
                                    error={
                                        "error": "workflow_unavailable",
                                        "message": "Workflow is not active or not found",
                                    },
                                )
                            except AppError:
                                logger.warning(
                                    "skipping unavailable-workflow transition for %s "
                                    "(state changed concurrently)",
                                    execution.id,
                                )
                            processed += 1
                            continue

                        try:
                            started = await service.start(
                                execution.organization_id, execution.id
                            )
                        except AppError:
                            logger.info(
                                "skipping execution %s (cancelled or claimed concurrently)",
                                execution.id,
                            )
                            continue

                        processed += 1
                        adapter = get_adapter(
                            workflow.execution_mode,
                            event_sink=partial(service.record_events, started),
                        )
                        await service.record_event(
                            started,
                            ExecutionEventType.ADAPTER_DISPATCHED,
                            adapter=workflow.execution_mode,
                        )
                        try:
                            output = await asyncio.wait_for(
                                adapter.execute(
                                    workflow_id=execution.workflow_id,
                                    execution_id=execution.id,
                                    input_data=execution.input,
                                    config=workflow.config,
                                    definition=workflow.definition,
                                ),
                                timeout=settings.EXECUTION_TIMEOUT_SECONDS,
                            )
                        except TimeoutError:
                            logger.warning(
                                "execution %s exceeded hard timeout (%ss)",
                                execution.id,
                                settings.EXECUTION_TIMEOUT_SECONDS,
                            )
                            await service.record_event(
                                started,
                                ExecutionEventType.TIMEOUT_GUARD,
                                timeout_seconds=settings.EXECUTION_TIMEOUT_SECONDS,
                            )
                            try:
                                await service.timeout(
                                    started.organization_id, started.id
                                )
                            except AppError:
                                logger.warning(
                                    "timeout transition skipped for %s (state changed)",
                                    execution.id,
                                )
                        except Exception as exc:
                            logger.exception(
                                "execution %s failed via %s adapter",
                                execution.id,
                                workflow.execution_mode,
                            )
                            try:
                                await service.fail(
                                    started.organization_id,
                                    started.id,
                                    error=adapter_error_payload(exc),
                                    schedule_retry=True,
                                )
                            except AppError:
                                logger.warning(
                                    "fail transition skipped for %s (state changed)",
                                    execution.id,
                                )
                        else:
                            await service.record_event(
                                started,
                                ExecutionEventType.ADAPTER_RETURNED,
                                adapter=workflow.execution_mode,
                            )
                            try:
                                await service.complete(
                                    started.organization_id,
                                    started.id,
                                    output=output,
                                )
                            except AppError:
                                logger.warning(
                                    "complete transition skipped for %s "
                                    "(cancelled concurrently or state changed)",
                                    execution.id,
                                )
                    await session.commit()
            get_counter(
                "execution_drained_total",
                description="Workflow executions drained from the queue",
            ).add(processed)
        cls._observe_phase("queued", start)
        return processed

    @classmethod
    async def timeout_stuck(cls) -> int:
        """Mark RUNNING executions that exceeded the timeout as timed out."""
        start = time.perf_counter()
        with span("automation.worker.timeouts"):
            async with async_session_factory() as session:
                service = WorkflowExecutionService(session)
                await cls._set_statement_timeout(session)
                executions = await service.get_stuck_running()
                transitioned = 0
                for execution in executions:
                    try:
                        await service.timeout(execution.organization_id, execution.id)
                    except AppError:
                        logger.info(
                            "timeout skipped for %s (already transitioned)",
                            execution.id,
                        )
                        continue
                    transitioned += 1
                await session.commit()
        cls._observe_phase("timeouts", start)
        return transitioned

    @classmethod
    async def schedule_tick(cls) -> int:
        """Dispatch due schedule triggers (isolated from the queue phases).

        Runs on its own cadence and owns its own session/transaction, so a
        failure here can never block or slow retries, queue draining, or
        timeout processing.
        """
        if not settings.SCHEDULE_DISPATCHER_ENABLED:
            return 0
        start = time.perf_counter()
        with span("automation.worker.schedule"):
            async with async_session_factory() as session:
                stats = await ScheduleDispatcher(session).dispatch_due()
        cls._observe_phase("schedule", start)
        return stats["queued"]

    @classmethod
    async def _automation_enabled(cls) -> bool:
        """Whether the automation kill switch is open (best-effort check).

        When the global kill switch is paused, queue/retry/schedule phases are
        skipped so no new work is dispatched. A failed check is treated as
        paused so a settings outage can never un-gate the worker.
        """
        try:
            with span("automation.worker.gate"):
                async with async_session_factory() as session:
                    return await AutomationControlService(session).is_enabled()
        except Exception:
            logger.exception("automation kill-switch check failed; assuming paused")
            return False

    @classmethod
    async def sweep(cls) -> dict[str, int]:
        """Run one full pass: retries + queued + timeouts (not schedules).

        While the global kill switch is paused only the timeout/housekeeping
        phase runs (it re-converges stale RUNNING rows without dispatching new
        work); retries and queue draining are skipped until automation resumes.
        """
        if not await cls._automation_enabled():
            timed_out = await cls.timeout_stuck()
            return {"retried": 0, "processed": 0, "timed_out": timed_out}
        retried = await cls.process_retries()
        processed = await cls.process_queued()
        timed_out = await cls.timeout_stuck()
        return {"retried": retried, "processed": processed, "timed_out": timed_out}

    @classmethod
    async def run_loop(cls) -> None:
        """Poll forever: the standalone worker entrypoint.

        Queue phases run on every iteration at ``EXECUTION_POLL_INTERVAL_SECONDS``;
        the schedule phase additionally runs only when its own cadence has
        elapsed, and its failures are contained so the queue is never delayed.
        Restart-safety relies on persisted DB state only (``last_fired_at`` +
        atomic reservations), so a crash mid-sweep leaves no orphan work.
        """
        logger.info(
            "execution worker starting (queue poll %ss, schedule poll %ss)",
            settings.EXECUTION_POLL_INTERVAL_SECONDS,
            settings.SCHEDULE_POLL_INTERVAL_SECONDS,
        )
        last_schedule_sweep = 0.0
        try:
            while True:
                loop_ok = True
                last_error: str | None = None
                try:
                    stats = await cls.sweep()
                    if any(stats.values()):
                        logger.info("execution worker sweep: %s", stats)
                except Exception:
                    loop_ok = False
                    last_error = "sweep failed"
                    logger.exception("execution worker sweep failed")

                if settings.SCHEDULE_DISPATCHER_ENABLED and (
                    time.monotonic() - last_schedule_sweep
                    >= settings.SCHEDULE_POLL_INTERVAL_SECONDS
                ):
                    last_schedule_sweep = time.monotonic()
                    try:
                        queued = await cls.schedule_tick()
                        if queued:
                            logger.info("schedule dispatcher queued %s execution(s)", queued)
                    except Exception:
                        loop_ok = False
                        last_error = "schedule tick failed"
                        logger.exception("schedule dispatcher tick failed")

                await cls.heartbeat(loop_ok=loop_ok, last_error=last_error)
                await asyncio.sleep(settings.EXECUTION_POLL_INTERVAL_SECONDS)
        except (KeyboardInterrupt, SystemExit):
            await cls.heartbeat(loop_ok=False, last_error="shutdown")
            logger.info("execution worker stopped")
            raise


def _worker_entrypoint() -> None:
    """Entrypoint for ``python -m app.workers.execution_worker``."""
    asyncio.run(ExecutionWorker.run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
