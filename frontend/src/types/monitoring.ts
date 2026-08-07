// Monitoring domain types mirroring backend/app/schemas/monitoring.py.
// Keep in sync with the backend response schemas.

import type {
  DatabaseHealth,
  ExecutionHistoryEntry,
  ExecutionHistoryResponse,
  ExecutionTimelineEvent,
  ExecutionTimelineResponse,
  HeartbeatFilters,
  MonitoringInformationResponse,
  OrganizationQueue,
  QueueMetrics,
  QueueStatusResponse,
  SystemHealth,
  WorkerHealthSummary,
} from "./index";

export type {
  DatabaseHealth,
  ExecutionHistoryEntry,
  ExecutionHistoryResponse,
  ExecutionTimelineEvent,
  ExecutionTimelineResponse,
  HeartbeatFilters,
  MonitoringInformationResponse,
  OrganizationQueue,
  QueueMetrics,
  QueueStatusResponse,
  SystemHealth,
  WorkerHealthSummary,
} from "./index";

/** Comprehensive operational summary (backend OperationalSummaryResponse). */
export interface OperationalSummaryResponse {
  timestamp: string;
  executions: Record<string, number>;
  events: Record<string, number>;
  workers: Record<string, unknown>;
  automation: Record<string, unknown>;
  schedules: Record<string, number>;
  system: Record<string, boolean>;
}

/** Execution statistics (backend ExecutionStatisticsResponse). */
export interface ExecutionStatisticsResponse {
  window_hours: number;
  counts_by_status: Record<string, number>;
  counts_by_workflow: Record<string, number>;
  counts_by_organization: Record<string, number>;
  total_executions: number;
}

/** A single worker health entry used in worker statistics and heartbeats. */
export interface WorkerHealthEntry {
  instance_id: string;
  worker_type: string;
  pid: number;
  hostname: string;
  last_heartbeat_at: string;
  loop_ok: boolean;
  last_error: string | null;
}

/** Worker health and activity statistics (backend WorkerStatisticsResponse). */
export interface WorkerStatisticsResponse {
  window_hours: number;
  active_workers: number;
  healthy_loops: number;
  errored_loops: number;
  health_percentage: number;
  errors_by_type: Record<string, number>;
  workers: WorkerHealthEntry[];
}

/** Schedule dispatch statistics (backend ScheduleStatisticsResponse). */
export interface ScheduleStatisticsResponse {
  window_hours: number;
  queued: number;
  failed: number;
  skipped: number;
  conflicts: number;
}

/** Retention worker statistics (backend RetentionStatisticsResponse). */
export interface RetentionStatisticsResponse {
  window_hours: number;
  executions_deleted: number;
  workers_pruned: number;
}

/** Current automation pause state (subset of backend current_status). */
export interface AutomationCurrentStatus {
  enabled: boolean;
  paused_by: string | null;
  paused_at: string | null;
  paused_reason: string | null;
}

/** Automation lifecycle statistics (backend AutomationLifecycleResponse). */
export interface AutomationLifecycleResponse {
  automation_paused_events: number;
  automation_resumed_events: number;
  current_status: AutomationCurrentStatus;
}

/** Worker heartbeat visibility entry (backend HeartbeatVisibilityResponse). */
export interface HeartbeatVisibilityResponse {
  instance_id: string;
  worker_type: string;
  pid: number;
  hostname: string;
  last_heartbeat_at: string;
  loop_ok: boolean;
  last_error: string | null;
  counters: Record<string, unknown> | null;
}
