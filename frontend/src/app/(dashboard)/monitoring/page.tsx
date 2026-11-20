// Canonical monitoring route (Batch 4).
//
// Composes the existing monitoring components into a permission-aware tabbed
// view. Permission boundaries follow the backend split exactly (D-12):
//   - Workspace metrics tab  -> AUTOMATION_READ (all roles)
//   - Infrastructure tab     -> AUTOMATION_MANAGE (owner/admin only, hidden otherwise)
//
// No Logs tab: no backend log endpoint exists (D-07). No hostnames, pids,
// secrets, or raw payloads are rendered for non-admin roles. The backend
// remains the definitive authorization boundary.
"use client";

import { useAuth } from "@/hooks/use-auth";
import { can } from "@/lib/permissions";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/ui/empty-state";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { useDeliveryStatistics } from "@/services/monitoring";
import { MonitoringErrorState } from "@/components/monitoring/monitoring-error-state";
import { OperationalSummaryCard } from "@/components/monitoring/operational-summary-card";
import { ExecutionStatisticsDisplay } from "@/components/monitoring/execution-statistics";
import { ExecutionTimelineDisplay } from "@/components/monitoring/execution-timeline";
import { ExecutionHistoryDisplay } from "@/components/monitoring/execution-history";
import { WorkerStatisticsDisplay } from "@/components/monitoring/worker-statistics";
import { ScheduleStatisticsDisplay } from "@/components/monitoring/schedule-statistics";
import { HeartbeatVisibilityDisplay } from "@/components/monitoring/heartbeat-display";
import { QueueStatusDisplay } from "@/components/monitoring/queue-status";
import { MonitoringInformationDisplay } from "@/components/monitoring/monitoring-information";
import { AutomationControls } from "@/components/monitoring/automation-controls";

export default function MonitoringPage() {
  const session = useAuth();
  const role = session?.user?.role;
  const canRead = !!role && can(role, "automation_read");
  const canManage = !!role && can(role, "automation_manage");

  if (!session) {
    return null;
  }

  if (!canRead) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Monitoring</h1>
        <EmptyState
          title="Access restricted"
          description="You do not have permission to view monitoring data."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Monitoring</h1>
        <p className="text-sm text-gray-500">
          Operational visibility into executions, workers, and automation. Data is refreshed
          periodically; nothing here is sent externally.
        </p>
      </div>

      <Tabs defaultValue="workspace" className="w-full">
        <TabsList>
          <TabsTrigger value="workspace">Workspace metrics</TabsTrigger>
          {canManage ? <TabsTrigger value="infrastructure">Infrastructure</TabsTrigger> : null}
        </TabsList>

        <TabsContent value="workspace">
          <div className="space-y-6">
            <OperationalSummaryCard />
            <ExecutionStatisticsDisplay />
            <QueueStatusDisplay />
            <MonitoringInformationDisplay />
            <ExecutionTimelineDisplay />
            <ExecutionHistoryDisplay />
          </div>
        </TabsContent>

        {canManage ? (
          <TabsContent value="infrastructure">
            <div className="space-y-6">
              <OperationalSummaryCard />
              <WorkerStatisticsDisplay />
              <ScheduleStatisticsDisplay />
              <HeartbeatVisibilityDisplay />
              <DeliveryStatisticsCard />
              <QueueStatusDisplay />
              <MonitoringInformationDisplay />
              <AutomationControls />
            </div>
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}

function DeliveryStatisticsCard() {
  const { data, isLoading, isError, error, refetch, isFetching } = useDeliveryStatistics();
  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Delivery statistics" description="Loading delivery outbox metrics…" />
        <CardBody>
          <div className="flex items-center gap-2 py-4">
            <Spinner label="Loading…" />
          </div>
        </CardBody>
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Card>
        <CardHeader title="Delivery statistics" description="Delivery outbox metrics" />
        <CardBody>
          <MonitoringErrorState
            message={error instanceof Error ? error.message : "Failed to load delivery statistics."}
            onRetry={() => refetch()}
            retrying={isFetching}
          />
        </CardBody>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader title="Delivery statistics" description="Delivery outbox metrics" />
      <CardBody>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="font-semibold">{data.queued}</span> queued
          </div>
          <div>
            <span className="font-semibold">{data.processing}</span> processing
          </div>
          <div>
            <span className="font-semibold">{data.retrying}</span> retrying
          </div>
          <div>
            <span className="font-semibold">{data.delivered}</span> delivered
          </div>
          <div>
            <span className="font-semibold">{data.failed}</span> failed
          </div>
          <div>
            <span className="font-semibold">{data.cancelled}</span> cancelled
          </div>
          <div>
            <span className="font-semibold">{data.active}</span> active
          </div>
          <div>
            <span className="font-semibold">{data.terminal}</span> terminal
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
