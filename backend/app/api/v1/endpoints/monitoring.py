"""Operational monitoring endpoints for production visibility.

Provides comprehensive monitoring APIs for automation infrastructure including
worker health, execution statistics, operational summaries, and runtime metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import ExecutionStatus
from app.schemas.monitoring import (
    AutomationLifecycleResponse,
    DeliveryStatisticsResponse,
    ExecutionHistoryResponse,
    ExecutionStatisticsResponse,
    ExecutionTimelineEvent,
    ExecutionTimelineResponse,
    HeartbeatVisibilityResponse,
    MonitoringInformationResponse,
    OperationalSummaryResponse,
    QueueStatusResponse,
    RetentionStatisticsResponse,
    ScheduleStatisticsResponse,
    WorkerStatisticsResponse,
)
from app.services.operational_monitoring_service import OperationalMonitoringService

if TYPE_CHECKING:
    pass

router = APIRouter()

# Admin-only dependencies for monitoring endpoints
_admin = Depends(require_permission(Permission.AUTOMATION_MANAGE))
_monitoring = Depends(require_permission(Permission.AUTOMATION_READ))


@router.get(
    "/operational/summary",
    response_model=OperationalSummaryResponse,
    summary="Get operational summary dashboard",
    dependencies=[_admin],
)
async def get_operational_summary(
    db: DbSession,
    current_user: CurrentUser,
) -> OperationalSummaryResponse:
    """Get comprehensive operational summary for production dashboards.

    Returns execution counts, worker health, automation status, schedule stats,
    and system health metrics.
    """
    service = OperationalMonitoringService(db)
    summary = await service.get_operational_summary()
    return OperationalSummaryResponse(**summary)


@router.get(
    "/execution-statistics",
    response_model=ExecutionStatisticsResponse,
    summary="Get execution statistics",
    dependencies=[_monitoring],
)
async def get_execution_statistics(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
) -> ExecutionStatisticsResponse:
    """Get detailed execution statistics for the specified time window.

    Returns counts by execution status, workflow distribution, and organization
    distribution.
    """
    service = OperationalMonitoringService(db)
    stats = await service.get_execution_statistics(hours)
    return ExecutionStatisticsResponse(**stats)


@router.get(
    "/delivery-statistics",
    response_model=DeliveryStatisticsResponse,
    summary="Platform-wide delivery outbox statistics",
    dependencies=[_admin],
)
async def get_delivery_statistics(
    db: DbSession,
    current_user: CurrentUser,
) -> DeliveryStatisticsResponse:
    """Get platform-wide delivery outbox statistics (all organizations).

    Returns counts by delivery status plus active/terminal totals. Gated by
    ``automation_manage`` (admin-only, consistent with operational summaries).
    """
    from app.services.delivery_service import DeliveryService

    service = DeliveryService(db)
    stats = await service.platform_statistics()
    return DeliveryStatisticsResponse(**stats)


@router.get(
    "/worker-statistics",
    response_model=WorkerStatisticsResponse,
    summary="Get worker statistics",
    dependencies=[_monitoring],
)
async def get_worker_statistics(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
) -> WorkerStatisticsResponse:
    """Get worker health and activity statistics.

    Returns worker counts, health status, error distribution, and detailed worker
    information.
    """
    service = OperationalMonitoringService(db)
    stats = await service.get_worker_statistics(hours)
    return WorkerStatisticsResponse(**stats)


@router.get(
    "/schedule-statistics",
    response_model=ScheduleStatisticsResponse,
    summary="Get schedule statistics",
    dependencies=[_monitoring],
)
async def get_schedule_statistics(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
) -> ScheduleStatisticsResponse:
    """Get schedule dispatch statistics.

    Returns schedule dispatcher metrics including queued, failed, skipped, and
    conflict counts.
    """
    service = OperationalMonitoringService(db)
    stats = await service.get_schedule_statistics(hours)
    return ScheduleStatisticsResponse(**stats)


@router.get(
    "/retention-statistics",
    response_model=RetentionStatisticsResponse,
    summary="Get retention statistics",
    dependencies=[_monitoring],
)
async def get_retention_statistics(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
) -> RetentionStatisticsResponse:
    """Get retention worker statistics.

    Returns retention sweep metrics including deleted execution events and
    pruned worker health records.
    """
    service = OperationalMonitoringService(db)
    stats = await service.get_retention_statistics(hours)
    return RetentionStatisticsResponse(**stats)


@router.get(
    "/automation-lifecycle",
    response_model=AutomationLifecycleResponse,
    summary="Get automation lifecycle statistics",
    dependencies=[_monitoring],
)
async def get_automation_lifecycle(
    db: DbSession,
    current_user: CurrentUser,
) -> AutomationLifecycleResponse:
    """Get automation lifecycle statistics including pause/resume events.

    Returns counts of automation pause/resume events and current automation
    status from the control service.
    """
    service = OperationalMonitoringService(db)
    lifecycle = await service.get_automation_lifecycle()
    return AutomationLifecycleResponse(**lifecycle)


@router.get(
    "/heartbeat-visibility",
    response_model=list[HeartbeatVisibilityResponse],
    summary="Get worker heartbeat visibility",
    dependencies=[_monitoring],
)
async def get_heartbeat_visibility(
    db: DbSession,
    current_user: CurrentUser,
    worker_type: str | None = Query(
        default=None,
        description="Filter by worker type (e.g., 'execution')",
    ),
    stale_within_seconds: int = Query(
        default=300, ge=60, le=86400, description="Staleness window in seconds"
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum results"),
) -> list[HeartbeatVisibilityResponse]:
    """Get worker heartbeat visibility for monitoring.

    Returns list of worker instances with their heartbeat status, useful for
    identifying stale or failed workers.
    """
    from app.services.monitoring_service import WorkerHealthService

    service = WorkerHealthService(db)
    workers = await service.list_alive(
        worker_type=worker_type,
        stale_within_seconds=stale_within_seconds,
        limit=limit,
    )

    return [
        HeartbeatVisibilityResponse(
            instance_id=worker.instance_id,
            worker_type=worker.worker_type,
            pid=worker.pid,
            hostname=worker.hostname,
            last_heartbeat_at=worker.last_heartbeat_at,
            loop_ok=worker.loop_ok,
            last_error=worker.last_error,
            counters=worker.counters,
        )
        for worker in workers
    ]


@router.get(
    "/execution-timeline",
    response_model=ExecutionTimelineResponse,
    summary="Get execution timeline events",
    dependencies=[_monitoring],
)
async def get_execution_timeline(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
    status: ExecutionStatus | None = Query(default=None, description="Filter by execution status"),
    workflow: str | None = Query(
        default=None, description="Filter by workflow name (partial match)"
    ),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum results"),
) -> ExecutionTimelineResponse:
    """Get recent execution timeline events across all organizations.

    Returns the latest execution events with workflow name and execution
    status/duration attached, optionally filtered by status or workflow.
    """
    service = OperationalMonitoringService(db)
    data = await service.get_execution_timeline(hours, status, workflow, limit)
    return ExecutionTimelineResponse(
        events=[ExecutionTimelineEvent(**event) for event in data["events"]]
    )


@router.get(
    "/execution-history",
    response_model=ExecutionHistoryResponse,
    summary="Get execution history",
    dependencies=[_monitoring],
)
async def get_execution_history(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=50, ge=1, le=200, description="Results per page"),
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
    status: ExecutionStatus | None = Query(default=None, description="Filter by execution status"),
    workflow: str | None = Query(
        default=None, description="Filter by workflow name (partial match)"
    ),
) -> ExecutionHistoryResponse:
    """Get paginated execution history across all organizations."""
    service = OperationalMonitoringService(db)
    data = await service.get_execution_history(page, page_size, hours, status, workflow)
    return ExecutionHistoryResponse(**data)


@router.get(
    "/queue-status",
    response_model=QueueStatusResponse,
    summary="Get queue status",
    dependencies=[_monitoring],
)
async def get_queue_status(
    db: DbSession,
    current_user: CurrentUser,
) -> QueueStatusResponse:
    """Get per-organization queue status across all organizations."""
    service = OperationalMonitoringService(db)
    data = await service.get_queue_status()
    return QueueStatusResponse(**data)


@router.get(
    "/monitoring-information",
    response_model=MonitoringInformationResponse,
    summary="Get comprehensive monitoring information",
    dependencies=[_monitoring],
)
async def get_monitoring_information(
    db: DbSession,
    current_user: CurrentUser,
) -> MonitoringInformationResponse:
    """Get comprehensive system, database, worker, and queue information."""
    service = OperationalMonitoringService(db)
    data = await service.get_monitoring_information()
    return MonitoringInformationResponse(**data)
