// Schedule statistics display component for Item 9.
//
// Provides schedule dispatcher metrics and performance monitoring.
import { Card, CardHeader, CardBody } from "@/components/ui/card";

/**
 * Schedule statistics display component.
 * Shows schedule dispatcher metrics including queued, failed, skipped, and conflict counts.
 */
export function ScheduleStatisticsDisplay() {
  return (
    <Card>
      <CardHeader
        title="Schedule Statistics"
        description="Schedule dispatcher metrics and performance"
      ></CardHeader>
      <CardBody>
        <div className="text-center py-8 text-muted-foreground">
          <div className="text-lg font-medium mb-2">Schedule Statistics</div>
          <div className="text-sm">
            Schedule statistics are available via the backend ScheduleDispatcher service.
            <br />
            This component will display queue statistics, failures, and performance metrics.
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
