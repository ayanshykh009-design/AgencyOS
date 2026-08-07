// React components for operational monitoring dashboard.
//
// Production-ready operational monitoring components for the AgencyOS automation platform.
// Provides real-time visibility into execution statistics, worker health, and automation status.
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatRelative } from "@/lib/format";

import { useExecutionStatistics } from "@/services/monitoring";
import { useWorkerStatistics } from "@/services/monitoring";
import { useAutomationLifecycle } from "@/services/monitoring";
import type { ExecutionStatisticsResponse } from "@/types/monitoring";
import type { WorkerStatisticsResponse } from "@/types/monitoring";
import type { AutomationLifecycleResponse } from "@/types/monitoring";

/**
 * Operational summary card component for the main dashboard.
 * Shows key operational metrics in a compact format.
 */
export function OperationalSummaryCard() {
  const { data: executionStats, isLoading: isLoadingExecutions } = useExecutionStatistics(1);
  const { data: workerStats, isLoading: isLoadingWorkers } = useWorkerStatistics(1);
  const { data: automationLifecycle, isLoading: isLoadingAutomation } = useAutomationLifecycle();

  if (isLoadingExecutions || isLoadingWorkers || isLoadingAutomation) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Operational Summary</CardTitle>
          <CardDescription>Loading operational data...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Operational Summary</CardTitle>
        <CardDescription>Real-time operational status</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {/* Execution Statistics */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Executions</h4>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="font-semibold">
                  {executionStats?.counts_by_status.queued || 0}
                </span>
                <span className="text-muted-foreground ml-1">queued</span>
              </div>
              <div>
                <span className="font-semibold">
                  {executionStats?.counts_by_status.running || 0}
                </span>
                <span className="text-muted-foreground ml-1">running</span>
              </div>
              <div>
                <span className="font-semibold">
                  {executionStats?.counts_by_status.succeeded || 0}
                </span>
                <span className="text-muted-foreground ml-1">completed</span>
              </div>
              <div>
                <span className="font-semibold">
                  {executionStats?.counts_by_status.failed || 0}
                </span>
                <span className="text-muted-foreground ml-1">failed</span>
              </div>
            </div>
          </div>

          {/* Worker Statistics */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Workers</h4>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Active:</span>
                <span className="font-semibold">{workerStats?.active_workers || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Healthy:</span>
                <span className="font-semibold">{workerStats?.healthy_loops || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Health %:</span>
                <span className="font-semibold">
                  {workerStats?.health_percentage?.toFixed(1) || 0}%
                </span>
              </div>
            </div>
          </div>

          {/* Automation Status */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Automation</h4>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status:</span>
                <Badge tone={automationLifecycle?.current_status.enabled ? "green" : "red"}>
                  {automationLifecycle?.current_status.enabled ? "Enabled" : "Paused"}
                </Badge>
              </div>
              {automationLifecycle?.current_status.paused_by && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Paused by:</span>
                  <span className="font-semibold">
                    {automationLifecycle.current_status.paused_by}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Recent Activity */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Recent</h4>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Paused events:</span>
                <span className="font-semibold">
                  {automationLifecycle?.automation_paused_events || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Resumed events:</span>
                <span className="font-semibold">
                  {automationLifecycle?.automation_resumed_events || 0}
                </span>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Detailed operational monitoring dashboard page.
 * Contains comprehensive monitoring information across all domains.
 */
export default function OperationalMonitoringPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Operational Monitoring</h1>
        <p className="text-muted-foreground">
          Real-time visibility into automation infrastructure, worker health, and execution
          statistics.
        </p>
      </div>

      {/* Main operational summary card */}
      <OperationalSummaryCard />

      {/* Detailed monitoring tabs */}
      <Tabs defaultValue="executions" className="space-y-4">
        <TabsList>
          <TabsTrigger value="executions">Executions</TabsTrigger>
          <TabsTrigger value="workers">Workers</TabsTrigger>
          <TabsTrigger value="automation">Automation</TabsTrigger>
          <TabsTrigger value="schedules">Schedules</TabsTrigger>
          <TabsTrigger value="retention">Retention</TabsTrigger>
        </TabsList>

        <TabsContent value="executions">
          <ExecutionStatisticsTab />
        </TabsContent>

        <TabsContent value="workers">
          <WorkerStatisticsTab />
        </TabsContent>

        <TabsContent value="automation">
          <AutomationLifecycleTab />
        </TabsContent>

        <TabsContent value="schedules">
          <ScheduleStatisticsTab />
        </TabsContent>

        <TabsContent value="retention">
          <RetentionStatisticsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * Execution statistics tab content.
 */
function ExecutionStatisticsTab() {
  const { data: executionStats, isLoading } = useExecutionStatistics(24);

  if (isLoading) {
    return <div className="text-center py-8">Loading execution statistics...</div>;
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Execution Statistics (Last 24 Hours)</CardTitle>
          <CardDescription>Breakdown by status and workflow distribution</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Status Distribution */}
            <div>
              <h4 className="text-lg font-semibold mb-4">Status Distribution</h4>
              <div className="space-y-2">
                {Object.entries(executionStats?.counts_by_status || {}).map(([status, count]) => (
                  <div key={status} className="flex justify-between items-center">
                    <span className="capitalize">{status}</span>
                    <Badge tone="gray">{count}</Badge>
                  </div>
                ))}
              </div>
            </div>

            {/* Workflow Distribution */}
            <div>
              <h4 className="text-lg font-semibold mb-4">Workflow Distribution</h4>
              <div className="space-y-2">
                {Object.entries(executionStats?.counts_by_workflow || {})
                  .slice(0, 5)
                  .map(([workflow, count]) => (
                    <div key={workflow} className="flex justify-between items-center">
                      <span className="truncate mr-2">{workflow}</span>
                      <Badge tone="gray">{count}</Badge>
                    </div>
                  ))}
                {Object.keys(executionStats?.counts_by_workflow || {}).length > 5 && (
                  <div className="text-sm text-muted-foreground">
                    +{Object.keys(executionStats?.counts_by_workflow || {}).length - 5} more
                    workflows
                  </div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Worker statistics tab content.
 */
function WorkerStatisticsTab() {
  const { data: workerStats, isLoading } = useWorkerStatistics(24);

  if (isLoading) {
    return <div className="text-center py-8">Loading worker statistics...</div>;
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Worker Statistics (Last 24 Hours)</CardTitle>
          <CardDescription>Worker health and activity metrics</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <h4 className="text-lg font-semibold">Summary</h4>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Active Workers:</span>
                  <span className="font-semibold">{workerStats?.active_workers}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Healthy Loops:</span>
                  <span className="font-semibold">{workerStats?.healthy_loops}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Errored Loops:</span>
                  <span className="font-semibold">{workerStats?.errored_loops}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Health Percentage:</span>
                  <span className="font-semibold">
                    {workerStats?.health_percentage?.toFixed(1) || 0}%
                  </span>
                </div>
              </div>
            </div>

            <div className="space-y-2 md:col-span-2">
              <h4 className="text-lg font-semibold">Error Types</h4>
              {Object.entries(workerStats?.errors_by_type || {}).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(workerStats?.errors_by_type || {})
                    .slice(0, 5)
                    .map(([error, count]) => (
                      <div key={error} className="flex justify-between items-center">
                        <span className="truncate mr-2">{error}</span>
                        <Badge tone="red">{count}</Badge>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  No errors recorded in the last 24 hours
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Individual worker details */}
      <Card>
        <CardHeader>
          <CardTitle>Worker Details</CardTitle>
          <CardDescription>Individual worker instances and their status</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {workerStats?.workers?.slice(0, 10).map((worker) => (
              <div
                key={worker.instance_id}
                className="flex items-center justify-between p-4 border rounded-lg"
              >
                <div className="flex-1">
                  <div className="font-medium">{worker.instance_id}</div>
                  <div className="text-sm text-muted-foreground">
                    {worker.hostname} (PID: {worker.pid})
                  </div>
                </div>
                <div className="text-right">
                  <Badge tone={worker.loop_ok ? "green" : "red"}>
                    {worker.loop_ok ? "Healthy" : "Error"}
                  </Badge>
                  <div className="text-xs text-muted-foreground mt-1">
                    Last heartbeat: {formatRelative(worker.last_heartbeat_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Automation lifecycle tab content.
 */
function AutomationLifecycleTab() {
  const { data: automationLifecycle, isLoading } = useAutomationLifecycle();

  if (isLoading) {
    return <div className="text-center py-8">Loading automation lifecycle...</div>;
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Automation Status</CardTitle>
          <CardDescription>Current automation enabled status and pause information</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Status:</span>
                <Badge tone={automationLifecycle?.current_status.enabled ? "green" : "red"}>
                  {automationLifecycle?.current_status.enabled ? "Enabled" : "Paused"}
                </Badge>
              </div>

              {automationLifecycle?.current_status.paused_by && (
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Paused by:</span>
                  <span className="font-medium">
                    {automationLifecycle.current_status.paused_by}
                  </span>
                </div>
              )}

              {automationLifecycle?.current_status.paused_at && (
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Paused at:</span>
                  <span className="font-medium">
                    {new Date(automationLifecycle.current_status.paused_at).toLocaleString()}
                  </span>
                </div>
              )}

              {automationLifecycle?.current_status.paused_reason && (
                <div className="space-y-2">
                  <span className="text-muted-foreground">Pause reason:</span>
                  <p className="text-sm font-medium italic">
                    &ldquo;{automationLifecycle.current_status.paused_reason}&rdquo;
                  </p>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <h4 className="text-lg font-semibold">Lifecycle Events (Last 24 Hours)</h4>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Automation paused events:</span>
                  <Badge tone="gray">{automationLifecycle?.automation_paused_events || 0}</Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Automation resumed events:</span>
                  <Badge tone="gray">{automationLifecycle?.automation_resumed_events || 0}</Badge>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Schedule statistics tab content.
 */
function ScheduleStatisticsTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Schedule Statistics</CardTitle>
        <CardDescription>Schedule dispatcher metrics and performance</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-center py-8 text-muted-foreground">
          Schedule statistics will be populated from the ScheduleDispatcher service.
          <br />
          This integration requires additional backend implementation.
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Retention statistics tab content.
 */
function RetentionStatisticsTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Retention Statistics</CardTitle>
        <CardDescription>Retention worker cleanup and deletion metrics</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-center py-8 text-muted-foreground">
          Retention statistics will be populated from the RetentionWorker service.
          <br />
          This integration requires additional backend implementation.
        </div>
      </CardContent>
    </Card>
  );
}
