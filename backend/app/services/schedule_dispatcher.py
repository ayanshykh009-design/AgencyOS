"""Schedule dispatcher: turn due schedule triggers into queued executions.

Runs as an isolated worker phase (see ``ExecutionWorker.schedule_tick``) so it
never blocks the execution queue. For every enabled schedule trigger on an
active workflow it:

1. computes the most recent cron fire time at or before now (UTC),
2. claims the tick with an atomic, optimistic reservation
   (``reserve_last_fired``) — exactly one worker instance wins per tick,
3. queues a workflow execution in the same transaction as the reservation, so
   the tick and the execution persist or roll back together.

That single-transaction claim makes dispatch restart-safe (a crash before
commit leaves no trace, a crash after commit cannot double-fire) and fully
idempotent (the optimistic guard refuses a second claim for the same tick).

Each trigger's reservation + queue runs inside its own savepoint, so a
per-trigger queue failure (e.g. the workflow was deactivated mid-batch) rolls
back only that trigger's reservation while earlier dispatches in the batch
survive to the caller's commit.

Every lifecycle event is emitted as a structured log line and a lightweight
metric counter (see ``app/core/metrics.py``).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.metrics import get_counter
from app.repositories.workflow_trigger import WorkflowTriggerRepository
from app.schemas.workflow_execution import WorkflowExecutionCreate
from app.services.automation_control_service import AutomationControlService
from app.services.base import utcnow
from app.services.schedule_cron import previous_fire
from app.services.workflow_execution_service import WorkflowExecutionService

logger = logging.getLogger("agencyos.automation.schedule")

_QUEUED = "schedule_dispatch_success"
_FAILED = "schedule_dispatch_failure"
_SKIPPED = "schedule_dispatch_skip"
_CONFLICT = "reservation_conflict"
_QUEUE_SUCCESS = "queue_success"
_QUEUE_FAILURE = "queue_failure"

_METRICS = (
    (_QUEUED, "Schedule triggers dispatched (execution queued)", "1"),
    (_FAILED, "Schedule triggers whose dispatch failed", "1"),
    (_SKIPPED, "Schedule triggers skipped (not due / invalid cron)", "1"),
    (_CONFLICT, "Schedule tick reservations lost to another worker", "1"),
    (_QUEUE_SUCCESS, "Workflow executions queued by the schedule dispatcher", "1"),
    (_QUEUE_FAILURE, "Workflow executions that failed to queue", "1"),
)
for _name, _description, _unit in _METRICS:
    get_counter(_name, _description, _unit)


def _log(event: str, **payload: Any) -> None:
    """Emit one structured JSON log line (rides in the ``message`` field)."""
    logger.info("schedule.%s %s", event, json.dumps({"event": event, **payload}))


class ScheduleDispatcher:
    """Owns the schedule-trigger dispatch business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._trigger_repo = WorkflowTriggerRepository(session)
        self._execution_service = WorkflowExecutionService(session)
        self._automation_control = AutomationControlService(session)

    async def dispatch_due(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> dict[str, int]:
        """Scan due schedule triggers, reserve ticks, and queue executions.

        Returns a summary dict with ``scanned``, ``queued``, ``failed``,
        ``skipped``, and ``conflicts`` counts. Raises on infrastructure
        failures; per-trigger failures are logged and counted, never raised.

        When the global kill switch is paused, dispatch is a no-op (returns
        zeroed stats) — due ticks are left for the next sweep after resume.
        """
        from app.core.config import settings

        if not await self._automation_control.is_enabled():
            _log("tick_skipped_automation_paused")
            return {"scanned": 0, "queued": 0, "failed": 0, "skipped": 0, "conflicts": 0}

        now = (now or utcnow()).astimezone(UTC)
        batch_limit = limit if limit is not None else settings.SCHEDULE_BATCH_LIMIT
        triggers = await self._trigger_repo.list_enabled_schedules(batch_limit)
        stats = {"scanned": len(triggers), "queued": 0, "failed": 0, "skipped": 0, "conflicts": 0}
        if not triggers:
            return stats

        _log("tick_start", count=len(triggers), limit=batch_limit)
        for trigger in triggers:
            if trigger.schedule_cron is None:
                _log(
                    "trigger_skipped",
                    trigger_id=str(trigger.id),
                    workflow_id=str(trigger.workflow_id),
                    organization_id=str(trigger.organization_id),
                    reason="missing_cron",
                    cron=None,
                )
                get_counter(_SKIPPED).add(1)
                stats["skipped"] += 1
                continue
            try:
                fire_time = previous_fire(trigger.schedule_cron, now)
            except ValueError:
                _log(
                    "trigger_skipped",
                    trigger_id=str(trigger.id),
                    workflow_id=str(trigger.workflow_id),
                    organization_id=str(trigger.organization_id),
                    reason="invalid_cron",
                    cron=trigger.schedule_cron,
                )
                get_counter(_SKIPPED).add(1)
                stats["skipped"] += 1
                continue

            if fire_time is None:
                _log(
                    "trigger_skipped",
                    trigger_id=str(trigger.id),
                    workflow_id=str(trigger.workflow_id),
                    organization_id=str(trigger.organization_id),
                    reason="cron_never_fires",
                    cron=trigger.schedule_cron,
                )
                get_counter(_SKIPPED).add(1)
                stats["skipped"] += 1
                continue

            if trigger.last_fired_at is not None and trigger.last_fired_at >= fire_time:
                _log(
                    "trigger_skipped",
                    trigger_id=str(trigger.id),
                    workflow_id=str(trigger.workflow_id),
                    organization_id=str(trigger.organization_id),
                    reason="not_due",
                    cron=trigger.schedule_cron,
                    prev_fire=fire_time.isoformat(),
                )
                get_counter(_SKIPPED).add(1)
                stats["skipped"] += 1
                continue

            _log(
                "trigger_detected",
                trigger_id=str(trigger.id),
                workflow_id=str(trigger.workflow_id),
                organization_id=str(trigger.organization_id),
                cron=trigger.schedule_cron,
                prev_fire=fire_time.isoformat(),
            )
            try:
                async with self._session.begin_nested():
                    reserved = await self._trigger_repo.reserve_last_fired(
                        trigger.id, fire_time, now
                    )
                    if not reserved:
                        _log(
                            "reservation_conflict",
                            trigger_id=str(trigger.id),
                            workflow_id=str(trigger.workflow_id),
                            organization_id=str(trigger.organization_id),
                            prev_fire=fire_time.isoformat(),
                        )
                        get_counter(_CONFLICT).add(1)
                        stats["conflicts"] += 1
                        continue

                    _log(
                        "reservation_success",
                        trigger_id=str(trigger.id),
                        workflow_id=str(trigger.workflow_id),
                        organization_id=str(trigger.organization_id),
                        prev_fire=fire_time.isoformat(),
                    )
                    try:
                        execution = await self._execution_service.queue(
                            WorkflowExecutionCreate(
                                organization_id=trigger.organization_id,
                                workflow_id=trigger.workflow_id,
                                trigger_id=trigger.id,
                                input={
                                    "trigger_config": trigger.config,
                                    "scheduled_at": fire_time.isoformat(),
                                },
                            ),
                            requested_by_user_id=None,
                        )
                    except AppError as exc:
                        # Workflow vanished/deactivated between listing and
                        # queueing: roll back this trigger's reservation so a
                        # later re-activation can re-fire the tick; never
                        # double-fire and never lose the rest of the batch.
                        _log(
                            "dispatch_failed",
                            trigger_id=str(trigger.id),
                            workflow_id=str(trigger.workflow_id),
                            organization_id=str(trigger.organization_id),
                            error=exc.code,
                        )
                        raise

                _log(
                    "workflow_queued",
                    trigger_id=str(trigger.id),
                    workflow_id=str(trigger.workflow_id),
                    organization_id=str(trigger.organization_id),
                    execution_id=str(execution.id),
                    prev_fire=fire_time.isoformat(),
                )
                get_counter(_QUEUED).add(1)
                get_counter(_QUEUE_SUCCESS).add(1)
                stats["queued"] += 1
            except AppError:
                # The savepoint rolled back this trigger's reservation and
                # queue attempt; earlier dispatches in the batch are
                # unaffected and persist on the caller's commit.
                get_counter(_FAILED).add(1)
                get_counter(_QUEUE_FAILURE).add(1)
                stats["failed"] += 1

        _log(
            "tick_end",
            scanned=stats["scanned"],
            queued=stats["queued"],
            failed=stats["failed"],
            skipped=stats["skipped"],
            conflicts=stats["conflicts"],
        )
        return stats
