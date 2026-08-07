// Monitoring API client for operational visibility.
//
// Provides TypeScript wrappers around the operational monitoring endpoints
// created in Item 8 (backend). Integrates with the existing monitoring APIs:
//
// - GET /monitoring/operational/summary
// - GET /monitoring/execution-statistics
// - GET /monitoring/worker-statistics
// - GET /monitoring/schedule-statistics
// - GET /monitoring/retention-statistics
// - GET /monitoring/automation-lifecycle
// - GET /monitoring/heartbeat-visibility
// - GET /monitoring/execution-timeline
// - GET /monitoring/execution-history
// - GET /monitoring/queue-status
// - GET /monitoring/monitoring-information
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import type {
  OperationalSummaryResponse,
  ExecutionStatisticsResponse,
  WorkerStatisticsResponse,
  ScheduleStatisticsResponse,
  RetentionStatisticsResponse,
  AutomationLifecycleResponse,
  HeartbeatVisibilityResponse,
  ExecutionTimelineResponse,
  ExecutionHistoryResponse,
  QueueStatusResponse,
  MonitoringInformationResponse,
  HeartbeatFilters,
} from "@/types/monitoring";

// Query keys for caching
export const monitoringKeys = {
  all: ["monitoring"] as const,
  summary: () => [...monitoringKeys.all, "summary"] as const,
  executionStats: (hours?: number) => [...monitoringKeys.all, "execution-stats", hours] as const,
  workerStats: (hours?: number) => [...monitoringKeys.all, "worker-stats", hours] as const,
  scheduleStats: (hours?: number) => [...monitoringKeys.all, "schedule-stats", hours] as const,
  retentionStats: (hours?: number) => [...monitoringKeys.all, "retention-stats", hours] as const,
  automationLifecycle: () => [...monitoringKeys.all, "automation-lifecycle"] as const,
  heartbeatVisibility: (filters?: HeartbeatFilters) =>
    [...monitoringKeys.all, "heartbeat-visibility", filters] as const,
  executionTimeline: (params?: { hours?: number; status?: string; workflow?: string }) =>
    [...monitoringKeys.all, "execution-timeline", params] as const,
  executionHistory: (params?: {
    page?: number;
    page_size?: number;
    hours?: number;
    status?: string;
    workflow?: string;
  }) => [...monitoringKeys.all, "execution-history", params] as const,
  queueStatus: () => [...monitoringKeys.all, "queue-status"] as const,
  monitoringInformation: () => [...monitoringKeys.all, "monitoring-information"] as const,
};

// API functions
const API_BASE = "/monitoring";

/**
 * Get comprehensive operational summary for production dashboards.
 * Requires AUTOMATION_MANAGE permission.
 */
export const getOperationalSummary = () => {
  return apiFetch<OperationalSummaryResponse>(`${API_BASE}/operational/summary`);
};

/**
 * Get execution statistics for the specified time window.
 * Requires AUTOMATION_READ permission.
 */
export const getExecutionStatistics = (hours: number = 24) => {
  return apiFetch<ExecutionStatisticsResponse>(`${API_BASE}/execution-statistics?hours=${hours}`);
};

/**
 * Get worker health and activity statistics.
 * Requires AUTOMATION_READ permission.
 */
export const getWorkerStatistics = (hours: number = 24) => {
  return apiFetch<WorkerStatisticsResponse>(`${API_BASE}/worker-statistics?hours=${hours}`);
};

/**
 * Get schedule dispatch statistics.
 * Requires AUTOMATION_READ permission.
 */
export const getScheduleStatistics = (hours: number = 24) => {
  return apiFetch<ScheduleStatisticsResponse>(`${API_BASE}/schedule-statistics?hours=${hours}`);
};

/**
 * Get retention worker statistics.
 * Requires AUTOMATION_READ permission.
 */
export const getRetentionStatistics = (hours: number = 24) => {
  return apiFetch<RetentionStatisticsResponse>(`${API_BASE}/retention-statistics?hours=${hours}`);
};

/**
 * Get automation lifecycle statistics including pause/resume events.
 * Requires AUTOMATION_READ permission.
 */
export const getAutomationLifecycle = () => {
  return apiFetch<AutomationLifecycleResponse>(`${API_BASE}/automation-lifecycle`);
};

/**
 * Get worker heartbeat visibility for monitoring.
 * Requires AUTOMATION_READ permission.
 */
export const getHeartbeatVisibility = (filters?: {
  worker_type?: string;
  stale_within_seconds?: number;
  limit?: number;
}) => {
  const searchParams = new URLSearchParams();
  if (filters?.worker_type) searchParams.append("worker_type", filters.worker_type);
  if (filters?.stale_within_seconds)
    searchParams.append("stale_within_seconds", filters.stale_within_seconds.toString());
  if (filters?.limit) searchParams.append("limit", filters.limit.toString());

  const queryString = searchParams.toString();
  const endpoint = `${API_BASE}/heartbeat-visibility${queryString ? `?${queryString}` : ""}`;

  return apiFetch<HeartbeatVisibilityResponse[]>(endpoint);
};

/**
 * Get execution timeline events.
 * Requires AUTOMATION_READ permission.
 */
export const getExecutionTimeline = (params?: {
  hours?: number;
  status?: string;
  workflow?: string;
}) => {
  const searchParams = new URLSearchParams();
  if (params?.hours) searchParams.append("hours", params.hours.toString());
  if (params?.status) searchParams.append("status", params.status);
  if (params?.workflow) searchParams.append("workflow", params.workflow);

  const queryString = searchParams.toString();
  const endpoint = `${API_BASE}/execution-timeline${queryString ? `?${queryString}` : ""}`;

  return apiFetch<ExecutionTimelineResponse>(endpoint);
};

/**
 * Get execution history with pagination.
 * Requires AUTOMATION_READ permission.
 */
export const getExecutionHistory = (params?: {
  page?: number;
  page_size?: number;
  hours?: number;
  status?: string;
  workflow?: string;
}) => {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.append("page", params.page.toString());
  if (params?.page_size) searchParams.append("page_size", params.page_size.toString());
  if (params?.hours) searchParams.append("hours", params.hours.toString());
  if (params?.status) searchParams.append("status", params.status);
  if (params?.workflow) searchParams.append("workflow", params.workflow);

  const queryString = searchParams.toString();
  const endpoint = `${API_BASE}/execution-history${queryString ? `?${queryString}` : ""}`;

  return apiFetch<ExecutionHistoryResponse>(endpoint);
};

/**
 * Get queue status.
 * Requires AUTOMATION_READ permission.
 */
export const getQueueStatus = () => {
  return apiFetch<QueueStatusResponse>(`${API_BASE}/queue-status`);
};

/**
 * Get monitoring information.
 * Requires AUTOMATION_READ permission.
 */
export const getMonitoringInformation = () => {
  return apiFetch<MonitoringInformationResponse>(`${API_BASE}/monitoring-information`);
};

/**
 * Pause automation (operator-only).
 * Requires AUTOMATION_MANAGE permission.
 */
export const pauseAutomation = (reason: string) => {
  return apiFetch(`/automation/pause`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
};

/**
 * Resume automation (operator-only).
 * Requires AUTOMATION_MANAGE permission.
 */
export const resumeAutomation = () => {
  return apiFetch(`/automation/resume`, {
    method: "POST",
  });
};

/**
 * Custom hook for operational summary with real-time updates.
 */
export const useOperationalSummary = () => {
  return useQuery({
    queryKey: monitoringKeys.summary(),
    queryFn: getOperationalSummary,
    refetchInterval: 30000, // Refresh every 30 seconds
    staleTime: 15000, // Consider data stale after 15 seconds
  });
};

/**
 * Custom hook for execution statistics with real-time updates.
 */
export const useExecutionStatistics = (hours: number = 24) => {
  return useQuery({
    queryKey: monitoringKeys.executionStats(hours),
    queryFn: () => getExecutionStatistics(hours),
    refetchInterval: 60000, // Refresh every minute
    staleTime: 30000,
  });
};

/**
 * Custom hook for worker statistics with real-time updates.
 */
export const useWorkerStatistics = (hours: number = 24) => {
  return useQuery({
    queryKey: monitoringKeys.workerStats(hours),
    queryFn: () => getWorkerStatistics(hours),
    refetchInterval: 15000, // Refresh every 15 seconds (workers change frequently)
    staleTime: 5000,
  });
};

/**
 * Custom hook for heartbeat visibility with real-time updates.
 */
export const useHeartbeatVisibility = (filters?: {
  worker_type?: string;
  stale_within_seconds?: number;
  limit?: number;
}) => {
  return useQuery({
    queryKey: monitoringKeys.heartbeatVisibility(filters),
    queryFn: () => getHeartbeatVisibility(filters),
    refetchInterval: 10000, // Refresh every 10 seconds
    staleTime: 3000,
    enabled: !!filters?.worker_type || true, // Always run if no specific worker type filter
  });
};

/**
 * Custom hook for automation lifecycle with real-time updates.
 */
export const useAutomationLifecycle = () => {
  return useQuery({
    queryKey: monitoringKeys.automationLifecycle(),
    queryFn: getAutomationLifecycle,
    refetchInterval: 120000, // Refresh every 2 minutes (pause/resume events are rare)
    staleTime: 60000,
  });
};

/**
 * Mutation hook for pausing automation.
 */
export const usePauseAutomation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: pauseAutomation,
    onSuccess: () => {
      // Invalidate relevant queries after a successful pause
      queryClient.invalidateQueries({ queryKey: monitoringKeys.all });
      queryClient.invalidateQueries({ queryKey: ["automation"] });
    },
  });
};

/**
 * Mutation hook for resuming automation.
 */
export const useResumeAutomation = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: resumeAutomation,
    onSuccess: () => {
      // Invalidate relevant queries after a successful resume
      queryClient.invalidateQueries({ queryKey: monitoringKeys.all });
      queryClient.invalidateQueries({ queryKey: ["automation"] });
    },
  });
};

/**
 * Custom hook for execution timeline with real-time updates.
 */
export const useExecutionTimeline = (params?: {
  hours?: number;
  status?: string;
  workflow?: string;
}) => {
  return useQuery({
    queryKey: monitoringKeys.executionTimeline(params),
    queryFn: () => getExecutionTimeline(params),
    refetchInterval: 60000, // Refresh every minute
    staleTime: 30000,
  });
};

/**
 * Custom hook for execution history with real-time updates.
 */
export const useExecutionHistory = (params?: {
  page?: number;
  page_size?: number;
  hours?: number;
  status?: string;
  workflow?: string;
}) => {
  return useQuery({
    queryKey: monitoringKeys.executionHistory(params),
    queryFn: () => getExecutionHistory(params),
    refetchInterval: 60000, // Refresh every minute
    staleTime: 30000,
  });
};

/**
 * Custom hook for queue status with real-time updates.
 */
export const useQueueStatus = (options?: { enabled?: boolean; refetchInterval?: number }) => {
  return useQuery({
    queryKey: monitoringKeys.queueStatus(),
    queryFn: getQueueStatus,
    refetchInterval: options?.refetchInterval ?? 15000,
    staleTime: 5000,
    enabled: options?.enabled ?? true,
  });
};

/**
 * Custom hook for monitoring information with real-time updates.
 */
export const useMonitoringInformation = () => {
  return useQuery({
    queryKey: monitoringKeys.monitoringInformation(),
    queryFn: getMonitoringInformation,
    refetchInterval: 60000, // Refresh every minute
    staleTime: 30000,
  });
};
