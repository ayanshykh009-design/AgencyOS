"""Monitoring schemas for operational visibility."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class OperationalSummaryResponse(BaseModel):
    """Comprehensive operational summary for production dashboards."""
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    executions: dict[str, int]
    events: dict[str, int]
    workers: dict[str, Any]
    automation: dict[str, Any]
    schedules: dict[str, int]
    system: dict[str, bool]


class ExecutionStatisticsResponse(BaseModel):
    """Execution statistics for time window analysis."""
    model_config = ConfigDict(from_attributes=True)

    window_hours: int
    counts_by_status: dict[str, int]
    counts_by_workflow: dict[str, int]
    counts_by_organization: dict[str, int]
    total_executions: int


class WorkerStatisticsResponse(BaseModel):
    """Worker health and activity statistics."""
    model_config = ConfigDict(from_attributes=True)

    window_hours: int
    active_workers: int
    healthy_loops: int
    errored_loops: int
    health_percentage: float
    errors_by_type: dict[str, int]
    workers: list[dict[str, Any]]


class ScheduleStatisticsResponse(BaseModel):
    """Schedule dispatch statistics."""
    model_config = ConfigDict(from_attributes=True)

    window_hours: int
    queued: int
    failed: int
    skipped: int
    conflicts: int


class RetentionStatisticsResponse(BaseModel):
    """Retention worker statistics."""
    model_config = ConfigDict(from_attributes=True)

    window_hours: int
    executions_deleted: int
    workers_pruned: int


class DeliveryStatisticsResponse(BaseModel):
    """Platform-wide delivery outbox statistics (monitoring)."""

    model_config = ConfigDict(from_attributes=True)

    queued: int
    processing: int
    retrying: int
    delivered: int
    failed: int
    cancelled: int
    active: int
    terminal: int


class AutomationLifecycleResponse(BaseModel):
    """Automation lifecycle statistics (pause/resume events)."""
    model_config = ConfigDict(from_attributes=True)

    automation_paused_events: int
    automation_resumed_events: int
    current_status: dict[str, Any]


class HeartbeatVisibilityResponse(BaseModel):
    """Worker heartbeat visibility for monitoring."""
    model_config = ConfigDict(from_attributes=True)

    instance_id: uuid.UUID
    worker_type: str
    pid: int
    hostname: str
    last_heartbeat_at: datetime
    loop_ok: bool
    last_error: str | None = None
    counters: dict[str, Any] | None = None


class ExecutionTimelineEvent(BaseModel):
    """Single execution timeline event (cross-organization)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    timestamp: datetime
    event_type: str
    status: str
    duration_ms: int | None = None


class ExecutionTimelineResponse(BaseModel):
    """Execution timeline across organizations."""
    model_config = ConfigDict(from_attributes=True)

    events: list[ExecutionTimelineEvent]


class ExecutionHistoryEntry(BaseModel):
    """Single execution history row (cross-organization)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    trigger_type: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    requested_by: str | None = None


class ExecutionHistoryResponse(BaseModel):
    """Paginated execution history across organizations."""
    model_config = ConfigDict(from_attributes=True)

    entries: list[ExecutionHistoryEntry]
    total: int


class OrganizationQueue(BaseModel):
    """Per-organization queue metrics."""
    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    organization_name: str
    queued_count: int
    running_count: int
    pending_count: int


class QueueStatusResponse(BaseModel):
    """Aggregate queue status across all organizations."""
    model_config = ConfigDict(from_attributes=True)

    total_queued: int
    total_running: int
    total_pending: int
    max_pending_per_org: int
    organization_queues: list[OrganizationQueue]


class SystemHealth(BaseModel):
    """System-level health and configuration summary."""
    model_config = ConfigDict(from_attributes=True)

    healthy: bool
    uptime: str
    version: str
    environment: str
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: str
    max_pending_per_org: int
    execution_timeout: int
    batch_size: int
    poll_interval: int
    retention_enabled: bool
    retention_days: int


class DatabaseHealth(BaseModel):
    """Database connection and pool health."""
    model_config = ConfigDict(from_attributes=True)

    connected: bool
    pool_usage: float
    active_connections: int
    avg_query_time: float


class WorkerHealthSummary(BaseModel):
    """Worker fleet health summary."""
    model_config = ConfigDict(from_attributes=True)

    total: int
    healthy: int
    unhealthy: int
    last_heartbeat: str | None = None


class QueueMetrics(BaseModel):
    """Queue processing metrics."""
    model_config = ConfigDict(from_attributes=True)

    total_queued: int
    running: int
    completed_24h: int
    failed_24h: int


class MonitoringInformationResponse(BaseModel):
    """Comprehensive monitoring information payload."""
    model_config = ConfigDict(from_attributes=True)

    system: SystemHealth
    database: DatabaseHealth
    workers: WorkerHealthSummary
    queue: QueueMetrics
