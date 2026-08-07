// Worker monitoring page - implements Item 9 worker status and health monitoring.
//
// Provides comprehensive worker monitoring with heartbeat visibility, statistics,
// and detailed worker information display.
import { WorkerStatisticsDisplay } from "@/components/monitoring/worker-statistics";
import { HeartbeatVisibilityDisplay } from "@/components/monitoring/heartbeat-display";

/**
 * Worker monitoring page for production visibility into worker health and status.
 * Displays worker statistics, heartbeat visibility, and detailed worker information.
 */
export default function WorkerMonitoringPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Worker Monitoring</h1>
        <p className="text-muted-foreground">
          Monitor worker health, heartbeat status, and operational metrics for all automation
          workers.
        </p>
      </div>

      {/* Worker Statistics Display */}
      <WorkerStatisticsDisplay />

      {/* Heartbeat Visibility Display */}
      <HeartbeatVisibilityDisplay />
    </div>
  );
}
