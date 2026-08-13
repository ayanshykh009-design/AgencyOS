"""Operational monitoring service for production visibility.

Aggregates statistics across execution, worker health, automation status,
and retention operations into operational dashboards and summaries.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import read_counter
from app.models.enums import ActivityEventType, ExecutionStatus
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.execution_event import ExecutionEventRepository
from app.repositories.workflow_event import WorkflowEventRepository
from app.repositories.workflow_execution import WorkflowExecutionRepository
from app.services.automation_control_service import AutomationControlService
from app.services.monitoring_service import WorkerHealthService

_PROCESS_STARTED_AT = time.monotonic()

# Prometheus counter names fed by the schedule dispatcher.
_SCHEDULE_COUNTERS = {
    "queued": "schedule_dispatch_success",
    "failed": "schedule_dispatch_failure",
    "skipped": "schedule_dispatch_skip",
    "conflicts": "reservation_conflict",
}

_EXECUTION_STATUSES = (
    ExecutionStatus.QUEUED,
    ExecutionStatus.RUNNING,
    ExecutionStatus.SUCCEEDED,
    ExecutionStatus.FAILED,
    ExecutionStatus.RETRYING,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.TIMED_OUT,
)


class OperationalMonitoringService:
    """Production operational visibility for automation infrastructure.

    Provides aggregated statistics and operational summaries across all major
    automation components (executions, workers, schedules, retention, automation
    control). Used for production dashboards and troubleshooting.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._execution_repo = WorkflowExecutionRepository(session)
        self._event_repo = ExecutionEventRepository(session)
        self._workflow_event_repo = WorkflowEventRepository(session)
        self._logs_repo = ActivityLogRepository(session)
        self._worker_service = WorkerHealthService(session)
        self._automation_control_service = AutomationControlService(session)

    async def get_operational_summary(self) -> dict[str, Any]:
        """Return comprehensive operational summary for production dashboards."""
        now = datetime.now(UTC)
        cutoff_24h = now - timedelta(hours=24)

        # Execution statistics (current state across all organizations).
        queued_count = await self._execution_repo.count_pending_all_orgs()
        running_count = await self._execution_repo.count_status(ExecutionStatus.RUNNING)
        completed_count = await self._execution_repo.count_status(ExecutionStatus.SUCCEEDED)
        failed_count = await self._execution_repo.count_status(ExecutionStatus.FAILED)
        timed_out_count = await self._execution_repo.count_status(ExecutionStatus.TIMED_OUT)
        cancelled_count = await self._execution_repo.count_status(ExecutionStatus.CANCELLED)
        retrying_count = await self._execution_repo.count_status(ExecutionStatus.RETRYING)

        # Event statistics (last 24 hours).
        events_last_24h = await self._event_repo.count_by_date_range(cutoff_24h)

        # Worker health statistics: active = heartbeated within 60s; stale =
        # heartbeats older than 3600s; total = both buckets.
        active_workers = await self._worker_service.list_alive(
            worker_type="execution",
            stale_within_seconds=60,
            limit=1000,
        )
        healthy_count = len(active_workers)
        stale_count = await self._worker_service.count_stale(
            stale_within_seconds=3600,
            worker_type="execution",
        )
        worker_total_count = healthy_count + stale_count

        # Automation control status.
        automation_status = await self._automation_control_service.get_status()

        # Workflow event statistics.
        events_queued = await self._workflow_event_repo.count_events_queued()
        events_consumed = await self._workflow_event_repo.count_events_consumed()
        fanout_truncated = read_counter("event_fanout_truncated")

        schedule_stats = {
            name: read_counter(counter) for name, counter in _SCHEDULE_COUNTERS.items()
        }

        return {
            "timestamp": now.isoformat(),
            "executions": {
                "queued": queued_count,
                "running": running_count,
                "completed": completed_count,
                "failed": failed_count,
                "timed_out": timed_out_count,
                "cancelled": cancelled_count,
                "retrying": retrying_count,
                "total_active": queued_count + running_count + retrying_count,
            },
            "events": {
                "last_24h": events_last_24h,
                "queued": events_queued,
                "consumed": events_consumed,
                "fanout_truncated": fanout_truncated,
            },
            "workers": {
                "healthy": healthy_count,
                "stale": stale_count,
                "total": worker_total_count,
                "health_percentage": (healthy_count / max(worker_total_count, 1)) * 100,
            },
            "automation": {
                "enabled": automation_status.enabled,
                "paused": not automation_status.enabled,
                "paused_by": automation_status.paused_by,
                "paused_at": automation_status.paused_at,
                "paused_reason": automation_status.paused_reason,
            },
            "schedules": schedule_stats,
            "system": {
                "database_connected": True,
                "retention_enabled": settings.EXECUTION_RETENTION_ENABLED,
                "worker_enabled": settings.EXECUTION_WORKER_ENABLED,
                "schedule_dispatcher_enabled": settings.SCHEDULE_DISPATCHER_ENABLED,
            },
        }

    async def get_execution_statistics(self, hours: int = 24) -> dict[str, Any]:
        """Get detailed execution statistics for the given time window."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        # Count executions by status in time window.
        stats: dict[str, int] = {}
        for status in _EXECUTION_STATUSES:
            count = await self._execution_repo.count_by_status_and_date(status, cutoff)
            stats[status.value] = count

        # Get workflow distribution (by name).
        workflow_counts = await self._execution_repo.count_by_workflow(cutoff)

        # Get organization distribution (by name).
        org_counts = await self._execution_repo.count_by_organization(cutoff)

        return {
            "window_hours": hours,
            "counts_by_status": stats,
            "counts_by_workflow": workflow_counts,
            "counts_by_organization": org_counts,
            "total_executions": sum(stats.values()),
        }

    async def get_worker_statistics(self, hours: int = 24) -> dict[str, Any]:
        """Get worker health and activity statistics."""
        workers = await self._worker_service.list_alive(
            worker_type="execution",
            stale_within_seconds=hours * 3600,
            limit=1000,
        )

        # Count by loop_ok status.
        healthy_loops = sum(1 for w in workers if w.loop_ok)
        errored_loops = sum(1 for w in workers if not w.loop_ok)

        # Get last error distribution.
        error_counts: dict[str, int] = {}
        for worker in workers:
            if worker.last_error:
                error_counts[worker.last_error] = error_counts.get(worker.last_error, 0) + 1

        return {
            "window_hours": hours,
            "active_workers": len(workers),
            "healthy_loops": healthy_loops,
            "errored_loops": errored_loops,
            "health_percentage": (healthy_loops / max(len(workers), 1)) * 100,
            "errors_by_type": error_counts,
            "workers": [
                {
                    "instance_id": str(worker.instance_id),
                    "worker_type": worker.worker_type,
                    "pid": worker.pid,
                    "hostname": worker.hostname,
                    "last_heartbeat_at": worker.last_heartbeat_at,
                    "loop_ok": worker.loop_ok,
                    "last_error": worker.last_error,
                    "counters": worker.counters,
                }
                for worker in workers
            ],
        }

    async def get_schedule_statistics(self, hours: int = 24) -> dict[str, int]:
        """Get schedule dispatch statistics (cumulative process counters)."""
        return {
            "window_hours": hours,
            **{name: read_counter(counter) for name, counter in _SCHEDULE_COUNTERS.items()},
        }

    async def get_retention_statistics(self, hours: int = 24) -> dict[str, int]:
        """Get retention worker statistics (cumulative process counters)."""
        return {
            "window_hours": hours,
            "executions_deleted": read_counter("retention_executions_deleted_total"),
            "workers_pruned": read_counter("retention_workers_pruned_total"),
        }

    async def get_automation_lifecycle(self) -> dict[str, Any]:
        """Get automation lifecycle statistics (pause/resume events)."""
        since = datetime.now(UTC) - timedelta(hours=24)
        paused_events = await self._logs_repo.count_by_event_type(
            ActivityEventType.AUTOMATION_PAUSED, since
        )
        resumed_events = await self._logs_repo.count_by_event_type(
            ActivityEventType.AUTOMATION_RESUMED, since
        )
        current_status = (await self._automation_control_service.get_status()).model_dump()

        return {
            "automation_paused_events": paused_events,
            "automation_resumed_events": resumed_events,
            "current_status": current_status,
        }

    async def get_execution_timeline(
        self,
        hours: int = 24,
        status: ExecutionStatus | None = None,
        workflow_name: str | None = None,
        limit: int = 100,
    ) -> dict[str, list[dict[str, Any]]]:
        """List recent execution timeline events across all organizations."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        events = await self._execution_repo.list_timeline(
            cutoff=cutoff,
            status=status,
            workflow_name=workflow_name,
            limit=limit,
        )

        return {
            "events": [
                {
                    "id": str(event.id),
                    "execution_id": str(event.execution_id),
                    "workflow_id": str(event.workflow_id),
                    "workflow_name": event.workflow.name if event.workflow else "Unknown workflow",
                    "timestamp": event.occurred_at.isoformat(),
                    "event_type": event.event_type.value,
                    "status": event.execution.status.value if event.execution else "unknown",
                    "duration_ms": event.execution.duration_ms if event.execution else None,
                }
                for event in events
            ]
        }

    async def get_execution_history(
        self,
        page: int = 1,
        page_size: int = 50,
        hours: int = 24,
        status: ExecutionStatus | None = None,
        workflow_name: str | None = None,
    ) -> dict[str, Any]:
        """List recent executions across all organizations with pagination."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        offset = max((page - 1) * page_size, 0)
        executions = await self._execution_repo.list_history(
            cutoff=cutoff,
            status=status,
            workflow_name=workflow_name,
            limit=page_size,
            offset=offset,
        )
        total = await self._execution_repo.count_history(
            cutoff=cutoff,
            status=status,
            workflow_name=workflow_name,
        )

        entries: list[dict[str, Any]] = []
        for execution in executions:
            # ``started_at`` is nullable for still-queued runs; fall back to the
            # creation timestamp so clients always receive a parsable value.
            started = execution.started_at or execution.created_at
            entries.append(
                {
                    "id": str(execution.id),
                    "execution_id": str(execution.id),
                    "workflow_id": str(execution.workflow_id),
                    "workflow_name": execution.workflow.name
                    if execution.workflow
                    else "Unknown workflow",
                    "trigger_type": execution.trigger.trigger_type.value
                    if execution.trigger
                    else None,
                    "status": execution.status.value,
                    "started_at": started.isoformat(),
                    "finished_at": execution.finished_at.isoformat()
                    if execution.finished_at
                    else None,
                    "duration_ms": execution.duration_ms,
                    "requested_by": execution.requested_by.email
                    if execution.requested_by
                    else None,
                }
            )

        return {"entries": entries, "total": total}

    async def get_queue_status(self) -> dict[str, Any]:
        """Get per-organization queue metrics across all organizations."""
        rows = await self._execution_repo.queue_status(limit=100)
        return {
            "total_queued": sum(row[2] for row in rows),
            "total_running": sum(row[3] for row in rows),
            "total_pending": sum(row[4] for row in rows),
            "max_pending_per_org": settings.EXECUTION_MAX_PENDING_PER_ORG,
            "organization_queues": [
                {
                    "organization_id": str(org_id),
                    "organization_name": name,
                    "queued_count": queued,
                    "running_count": running,
                    "pending_count": pending,
                }
                for org_id, name, queued, running, pending in rows
            ],
        }

    async def get_monitoring_information(self) -> dict[str, Any]:
        """Get comprehensive system health, worker, and queue information."""
        workers = await self._worker_service.list_alive(
            worker_type="execution",
            stale_within_seconds=3600,
            limit=1000,
        )
        healthy = sum(1 for w in workers if w.loop_ok)
        last_heartbeat = max((w.last_heartbeat_at for w in workers), default=None)

        cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
        completed_24h = await self._execution_repo.count_by_status_and_date(
            ExecutionStatus.SUCCEEDED, cutoff_24h
        )
        failed_24h = await self._execution_repo.count_by_status_and_date(
            ExecutionStatus.FAILED, cutoff_24h
        )
        queued = await self._execution_repo.count_pending_all_orgs()
        running = await self._execution_repo.count_status(ExecutionStatus.RUNNING)

        return {
            "system": {
                "healthy": True,
                "uptime": self._format_uptime(),
                "version": settings.APP_VERSION,
                "environment": settings.APP_ENV,
                "cpu_usage": self._cpu_usage(),
                "memory_usage": self._memory_usage(),
                "disk_usage": self._disk_usage(),
                "network_io": "",
                "max_pending_per_org": settings.EXECUTION_MAX_PENDING_PER_ORG,
                "execution_timeout": settings.EXECUTION_TIMEOUT_SECONDS,
                "batch_size": settings.EXECUTION_BATCH_SIZE,
                "poll_interval": settings.EXECUTION_POLL_INTERVAL_SECONDS,
                "retention_enabled": settings.EXECUTION_RETENTION_ENABLED,
                "retention_days": settings.EXECUTION_EVENT_RETENTION_DAYS,
            },
            "database": {
                "connected": True,
                "pool_usage": self._pool_usage(),
                "active_connections": 0,
                "avg_query_time": 0.0,
            },
            "workers": {
                "total": len(workers),
                "healthy": healthy,
                "unhealthy": len(workers) - healthy,
                "last_heartbeat": last_heartbeat.isoformat() if last_heartbeat else None,
            },
            "queue": {
                "total_queued": queued,
                "running": running,
                "completed_24h": completed_24h,
                "failed_24h": failed_24h,
            },
        }

    @staticmethod
    def _format_uptime() -> str:
        """Human-readable process uptime (e.g. ``3d 04h``)."""
        seconds = int(time.monotonic() - _PROCESS_STARTED_AT)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        return f"{days}d {hours:02d}h {minutes:02d}m"

    @staticmethod
    def _cpu_usage() -> float:
        """Best-effort CPU usage; 0.0 when the platform exposes no loadavg."""
        loadavg = getattr(os, "getloadavg", None)
        if loadavg is None:
            return 0.0
        try:
            load = loadavg()[0]
        except (AttributeError, OSError, IndexError):
            return 0.0
        return round(load, 1)

    @staticmethod
    def _memory_usage() -> float:
        """Best-effort memory usage; 0.0 without platform tooling (no psutil)."""
        return 0.0

    @staticmethod
    def _disk_usage() -> float:
        """Disk usage percentage of the backend volume (cross-platform)."""
        import shutil

        try:
            usage = shutil.disk_usage(".")
        except OSError:
            return 0.0
        return round((usage.used / usage.total) * 100, 1)

    @staticmethod
    def _pool_usage() -> float:
        """SQLAlchemy async pool utilization percentage (0.0 if not asyncpg)."""
        try:
            from app.core.database import engine

            pool = getattr(engine, "pool", None)
            if pool is None or not hasattr(pool, "checkedout"):
                return 0.0
            total = pool.size() + pool.overflow() or 1
            return round((pool.checkedout() / total) * 100, 1)
        except Exception:  # pragma: no cover - defensive introspection
            return 0.0
