"""Operational monitoring endpoints for production visibility.

Provides monitoring APIs for automation infrastructure including worker
health, execution statistics, operational summaries, and runtime metrics.

**Tenant isolation (B-2).** Tenant-data endpoints (executions, queue,
delivery statistics, lifecycle events) are org-scoped: the handler passes
``current_user.organization_id`` into the service and the repository layer
filters every aggregate by it. Infrastructure-level endpoints (worker
heartbeats, process counters, scheduler/retention counters) expose no tenant
rows but are gated behind ``AUTOMATION_MANAGE`` (admin-only) because they
disclose hostnames, pids, and process internals.
"""

from __future__ import annotations

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

router = APIRouter()

# Tenant-data monitoring: readable by any authenticated role; data is
# org-scoped by the handler (AUTOMATION_READ == all roles in the matrix).
_monitoring = Depends(require_permission(Permission.AUTOMATION_READ))
# Infrastructure-level / platform-sensitive views: admin-only.
_admin = Depends(require_permission(Permission.AUTOMATION_MANAGE))


@router.get(
    "/operational/summary",
    response_model=OperationalSummaryResponse,
    summary="Get operational summary dashboard (own organization)",
    dependencies=[_admin],
)
async def get_operational_summary(
    db: DbSession,
    current_user: CurrentUser,
) -> OperationalSummaryResponse:
    """Operational summary for the caller's organization.

    Returns execution counts, worker health, automation status, schedule stats,
    and system health metrics. Execution/event aggregates are org-scoped.
    """
    service = OperationalMonitoringService(db)
    summary = await service.get_operational_summary(current_user.organization_id)
    return OperationalSummaryResponse(**summary)


@router.get(
    "/execution-statistics",
    response_model=ExecutionStatisticsResponse,
    summary="Get execution statistics (own organization)",
    dependencies=[_monitoring],
)
async def get_execution_statistics(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
) -> ExecutionStatisticsResponse:
    """Execution statistics for the caller's organization.

    Returns counts by execution status, workflow distribution, and the
    caller's own organization distribution.
    """
    service = OperationalMonitoringService(db)
    stats = await service.get_execution_statistics(current_user.organization_id, hours)
    return ExecutionStatisticsResponse(**stats)


@router.get(
    "/delivery-statistics",
    response_model=DeliveryStatisticsResponse,
    summary="Delivery outbox statistics (own organization)",
    dependencies=[_admin],
)
async def get_delivery_statistics(
    db: DbSession,
    current_user: CurrentUser,
) -> DeliveryStatisticsResponse:
    """Delivery outbox statistics for the caller's organization.

    Returns counts by delivery status plus active/terminal totals. Org-scoped:
    a tenant admin must never see another organization's delivery volume.
    Gated by ``automation_manage`` (admin-only).
    """
    from app.services.delivery_service import DeliveryService

    service = DeliveryService(db)
    stats = await service.platform_statistics(current_user.organization_id)
    return DeliveryStatisticsResponse(**stats)


@router.get(
    "/worker-statistics",
    response_model=WorkerStatisticsResponse,
    summary="Get worker statistics (infrastructure)",
    dependencies=[_admin],
)
async def get_worker_statistics(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
) -> WorkerStatisticsResponse:
    """Worker health and activity statistics (infrastructure level).

    Returns worker counts, health status, error distribution, and detailed
    worker information (hostnames/pids). Admin-only.
    """
    service = OperationalMonitoringService(db)
    stats = await service.get_worker_statistics(hours)
    return WorkerStatisticsResponse(**stats)


@router.get(
    "/schedule-statistics",
    response_model=ScheduleStatisticsResponse,
    summary="Get schedule statistics (infrastructure)",
    dependencies=[_admin],
)
async def get_schedule_statistics(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
) -> ScheduleStatisticsResponse:
    """Schedule dispatch statistics (cumulative process counters). Admin-only."""
    service = OperationalMonitoringService(db)
    stats = await service.get_schedule_statistics(hours)
    return ScheduleStatisticsResponse(**stats)


@router.get(
    "/retention-statistics",
    response_model=RetentionStatisticsResponse,
    summary="Get retention statistics (infrastructure)",
    dependencies=[_admin],
)
async def get_retention_statistics(
    db: DbSession,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
) -> RetentionStatisticsResponse:
    """Retention worker statistics (cumulative process counters). Admin-only."""
    service = OperationalMonitoringService(db)
    stats = await service.get_retention_statistics(hours)
    return RetentionStatisticsResponse(**stats)


@router.get(
    "/automation-lifecycle",
    response_model=AutomationLifecycleResponse,
    summary="Get automation lifecycle statistics (own organization)",
    dependencies=[_monitoring],
)
async def get_automation_lifecycle(
    db: DbSession,
    current_user: CurrentUser,
) -> AutomationLifecycleResponse:
    """Automation pause/resume event counts for the caller's organization."""
    service = OperationalMonitoringService(db)
    lifecycle = await service.get_automation_lifecycle(current_user.organization_id)
    return AutomationLifecycleResponse(**lifecycle)


@router.get(
    "/heartbeat-visibility",
    response_model=list[HeartbeatVisibilityResponse],
    summary="Get worker heartbeat visibility (infrastructure)",
    dependencies=[_admin],
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
    """Worker heartbeat visibility (hostnames/pids). Admin-only."""
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
    summary="Get execution timeline events (own organization)",
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
    """Recent execution timeline events for the caller's organization."""
    service = OperationalMonitoringService(db)
    data = await service.get_execution_timeline(
        current_user.organization_id, hours, status, workflow, limit
    )
    return ExecutionTimelineResponse(
        events=[ExecutionTimelineEvent(**event) for event in data["events"]]
    )


@router.get(
    "/execution-history",
    response_model=ExecutionHistoryResponse,
    summary="Get execution history (own organization)",
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
    """Paginated execution history for the caller's organization."""
    service = OperationalMonitoringService(db)
    data = await service.get_execution_history(
        current_user.organization_id, page, page_size, hours, status, workflow
    )
    return ExecutionHistoryResponse(**data)


@router.get(
    "/queue-status",
    response_model=QueueStatusResponse,
    summary="Get queue status (own organization)",
    dependencies=[_monitoring],
)
async def get_queue_status(
    db: DbSession,
    current_user: CurrentUser,
) -> QueueStatusResponse:
    """Queue status for the caller's organization only."""
    service = OperationalMonitoringService(db)
    data = await service.get_queue_status(current_user.organization_id)
    return QueueStatusResponse(**data)


@router.get(
    "/monitoring-information",
    response_model=MonitoringInformationResponse,
    summary="Get monitoring information (org-scoped queue)",
    dependencies=[_monitoring],
)
async def get_monitoring_information(
    db: DbSession,
    current_user: CurrentUser,
) -> MonitoringInformationResponse:
    """System, database, worker, and queue information (queue is org-scoped)."""
    service = OperationalMonitoringService(db)
    data = await service.get_monitoring_information(current_user.organization_id)
    return MonitoringInformationResponse(**data)
