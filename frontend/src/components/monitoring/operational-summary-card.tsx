// Operational Summary Card component for Item 9.
//
// Compact dashboard widget showing key operational metrics at a glance.
// Designed to be embedded in the main dashboard.
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { useExecutionStatistics } from "@/services/monitoring";
import { useWorkerStatistics } from "@/services/monitoring";
import { useAutomationLifecycle } from "@/services/monitoring";
import { useQueueStatus } from "@/services/monitoring";

/**
 * Operational summary card component for the main dashboard.
 * Shows key operational metrics in a compact format for quick visibility.
 */
export function OperationalSummaryCard() {
  const { data: executionStats, isLoading: isLoadingExecutions } = useExecutionStatistics(1);
  const { data: workerStats, isLoading: isLoadingWorkers } = useWorkerStatistics(1);
  const { data: automationLifecycle, isLoading: isLoadingAutomation } = useAutomationLifecycle();
  const { data: queueStatus, isLoading: isLoadingQueue } = useQueueStatus();

  const isLoading =
    isLoadingExecutions || isLoadingWorkers || isLoadingAutomation || isLoadingQueue;

  if (isLoading) {
    return (
      <Card className="h-full">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Operational Summary</CardTitle>
          <CardDescription className="text-xs">Real-time operational metrics</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-muted-foreground text-sm">Loading...</div>
        </CardContent>
      </Card>
    );
  }

  const isPaused = automationLifecycle?.current_status?.enabled === false;
  const totalExecutions = executionStats?.total_executions || 0;
  const activeWorkers = workerStats?.active_workers || 0;
  const healthPct = workerStats?.health_percentage || 0;
  const queuedCount = queueStatus?.total_queued || 0;
  const runningCount = queueStatus?.total_running || 0;

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg">Operational Summary</CardTitle>
            <CardDescription className="text-xs">Real-time operational metrics</CardDescription>
          </div>
          <Badge tone={isPaused ? "red" : "green"} className="text-xs">
            {isPaused ? "PAUSED" : "ENABLED"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {/* Row 1: Executions & Queue */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-muted/50 rounded-lg">
            <div className="text-xs text-muted-foreground">Executions (1h)</div>
            <div className="text-2xl font-bold">{totalExecutions}</div>
          </div>
          <div className="p-3 bg-muted/50 rounded-lg">
            <div className="text-xs text-muted-foreground">Queue (Queued/Running)</div>
            <div className="text-2xl font-bold">
              {queuedCount} / {runningCount}
            </div>
          </div>
        </div>

        {/* Row 2: Workers & Automation */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-muted/50 rounded-lg">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Active Workers</span>
              <Badge
                tone={healthPct >= 90 ? "green" : healthPct >= 50 ? "amber" : "red"}
                className="text-xs"
              >
                {activeWorkers}
              </Badge>
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Health: {healthPct.toFixed(0)}%
            </div>
          </div>
          <div className="p-3 bg-muted/50 rounded-lg">
            <div className="text-xs text-muted-foreground">Automation</div>
            <div className="flex items-center justify-between">
              <span className="font-medium capitalize">{isPaused ? "paused" : "enabled"}</span>
              {automationLifecycle?.current_status.paused_by && (
                <span className="text-xs text-muted-foreground">
                  by {automationLifecycle.current_status.paused_by}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Quick Actions - shown only when automation is enabled */}
        {!isPaused && (
          <div className="pt-2 border-t">
            <button className="w-full text-xs text-muted-foreground hover:text-foreground transition-colors">
              View Full Dashboard →
            </button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
