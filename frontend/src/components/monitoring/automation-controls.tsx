"use client";

// Automation controls component for Item 9.
//
// Provides admin-only pause/resume controls for automation infrastructure.
// Follows the existing permission patterns and UI conventions.
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";

import { useAutomationLifecycle } from "@/services/monitoring";
import { usePauseAutomation, useResumeAutomation } from "@/services/monitoring";
import { PermissionGuard } from "@/components/auth/permission-guard";
import { Permission } from "@/lib/constants";

/**
 * Automation controls component for managing automation lifecycle.
 * Includes pause/resume functionality with confirmation dialogs and feedback.
 */
export function AutomationControls() {
  const [pauseReason, setPauseReason] = useState<string>("");
  const [isPauseDialogOpen, setIsPauseDialogOpen] = useState<boolean>(false);
  const [isResumeDialogOpen, setIsResumeDialogOpen] = useState<boolean>(false);

  const { data: automationLifecycle, isLoading: isLoadingLifecycle } = useAutomationLifecycle();
  const pauseMutation = usePauseAutomation();
  const resumeMutation = useResumeAutomation();

  const handlePause = async () => {
    if (!pauseReason.trim()) {
      alert("Please provide a reason for pausing automation");
      return;
    }

    try {
      await pauseMutation.mutateAsync(pauseReason);
      alert("Automation paused successfully");
      setIsPauseDialogOpen(false);
      setPauseReason("");
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to pause automation");
    }
  };

  const handleResume = async () => {
    try {
      await resumeMutation.mutateAsync();
      alert("Automation resumed successfully");
      setIsResumeDialogOpen(false);
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to resume automation");
    }
  };

  const isCurrentlyPaused = automationLifecycle?.current_status?.enabled === false;

  if (isLoadingLifecycle) {
    return (
      <Card>
        <CardHeader
          title="Automation Controls"
          description="Loading automation status..."
        ></CardHeader>
        <CardBody>
          <div className="text-center py-4">Loading...</div>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Automation Controls"
        description="Manage automation lifecycle (pause/resume operations)"
      ></CardHeader>
      <CardBody className="space-y-6">
        {/* Current Status */}
        <div className="space-y-4">
          <h4 className="text-lg font-semibold">Current Status</h4>
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div>
              <div className="font-medium">Automation Status</div>
              <div className="text-sm text-muted-foreground">
                {isCurrentlyPaused ? "Currently paused" : "Currently enabled"}
              </div>
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

        <Separator />

        {/* Control Buttons */}
        <div className="space-y-4">
          <h4 className="text-lg font-semibold">Control Actions</h4>

          {isCurrentlyPaused ? (
            <PermissionGuard permission={Permission.AUTOMATION_MANAGE}>
              <div>
                <button
                  onClick={() => setIsResumeDialogOpen(true)}
                  className="w-full px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
                  disabled={false}
                >
                  Resume Automation
                </button>
                {isResumeDialogOpen && (
                  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
                      <h3 className="text-lg font-semibold mb-4">Resume Automation</h3>
                      <p className="text-sm text-muted-foreground mb-4">
                        Are you sure you want to resume automation? This will re-enable all workflow
                        executions, schedule dispatches, and event processing.
                      </p>
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => setIsResumeDialogOpen(false)}
                          className="px-4 py-2 border rounded hover:bg-gray-100"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => {
                            handleResume();
                            setIsResumeDialogOpen(false);
                          }}
                          className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                        >
                          Resume Automation
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </PermissionGuard>
          ) : (
            <PermissionGuard permission={Permission.AUTOMATION_MANAGE}>
              <div>
                <button
                  onClick={() => setIsPauseDialogOpen(true)}
                  className="w-full px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
                  disabled={false}
                >
                  Pause Automation
                </button>
                {isPauseDialogOpen && (
                  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
                      <h3 className="text-lg font-semibold mb-4">Pause Automation</h3>
                      <p className="text-sm text-muted-foreground mb-4">
                        Are you sure you want to pause automation? This will immediately block all
                        workflow executions, schedule dispatches, and event processing. Only an
                        admin can resume.
                      </p>
                      <div className="mb-4">
                        <Label htmlFor="pause-reason" className="mb-2 block">
                          Pause Reason <span className="text-red-500">*</span>
                        </Label>
                        <input
                          id="pause-reason"
                          type="text"
                          value={pauseReason}
                          onChange={(e) => setPauseReason(e.target.value)}
                          placeholder="Enter reason for pausing automation..."
                          className="w-full px-3 py-2 border rounded-md"
                          required
                        />
                      </div>
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => setIsPauseDialogOpen(false)}
                          className="px-4 py-2 border rounded hover:bg-gray-100"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => {
                            handlePause();
                            setIsPauseDialogOpen(false);
                          }}
                          className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
                        >
                          Pause Automation
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </PermissionGuard>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
