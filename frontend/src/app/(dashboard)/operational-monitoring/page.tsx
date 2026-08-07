// Automation status page - Item 9 implementation.
//
// Provides automation status monitoring with pause/resume controls and detailed status information.
"use client";

import { useAutomationLifecycle } from "@/services/monitoring";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardBody } from "@/components/ui/card";

/**
 * Automation status page for operational visibility.
 * Shows current automation status, pause information, and control buttons.
 */
export default function AutomationStatusPage() {
  const { data: automationLifecycle, isLoading } = useAutomationLifecycle();

  if (isLoading) {
    return (
      <Card>
        <CardHeader
          title="Automation Status"
          description="Loading automation status..."
        ></CardHeader>
        <CardBody>
          <div className="text-center py-8">Loading automation status...</div>
        </CardBody>
      </Card>
    );
  }

  const isCurrentlyPaused = automationLifecycle?.current_status?.enabled === false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Automation Status</h1>
        <p className="text-muted-foreground">
          Monitor and control automation status across the platform.
        </p>
      </div>

      {/* Current Status Card */}
      <Card>
        <CardHeader
          title="Current Automation Status"
          description="Real-time status of automation across all environments"
        ></CardHeader>
        <CardBody>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <div className="font-medium">Overall Status</div>
                  <div className="text-sm text-muted-foreground">Current automation state</div>
                </div>
                <Badge tone={isCurrentlyPaused ? "red" : "green"} className="text-lg">
                  {isCurrentlyPaused ? "PAUSED" : "ENABLED"}
                </Badge>
              </div>

              {isCurrentlyPaused && automationLifecycle?.current_status.paused_by && (
                <div className="flex items-center justify-between p-4 border rounded-lg">
                  <div>
                    <div className="font-medium">Paused By</div>
                    <div className="text-sm text-muted-foreground">
                      {automationLifecycle.current_status.paused_by}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-medium">Paused At</div>
                    <div className="text-sm text-muted-foreground">
                      {automationLifecycle.current_status.paused_at &&
                        new Date(automationLifecycle.current_status.paused_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              )}

              {isCurrentlyPaused && automationLifecycle?.current_status.paused_reason && (
                <div className="p-4 border rounded-lg bg-muted/50">
                  <div className="font-medium mb-2">Pause Reason</div>
                  <div className="text-sm italic">
                    &ldquo;{automationLifecycle.current_status.paused_reason}&rdquo;
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <h4 className="text-lg font-semibold">Quick Actions</h4>
              <div className="text-sm text-muted-foreground">
                Automation is currently {isCurrentlyPaused ? "paused" : "running"}.
              </div>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
