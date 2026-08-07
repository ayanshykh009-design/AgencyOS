"use client";

// Queue Status component for Item 9.
//
// Displays real-time queue statistics including pending, running, and backlog metrics.
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useQueueStatus } from "@/services/monitoring";
import type { QueueStatusResponse } from "@/types/monitoring";

/**
 * Queue status display component.
 * Shows real-time queue metrics including organization-level breakdown.
 */
export function QueueStatusDisplay() {
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [refreshInterval, setRefreshInterval] = useState<number>(15000);

  const {
    data: queueStatus,
    isLoading,
    error,
    refetch,
  } = useQueueStatus({
    enabled: autoRefresh,
    refetchInterval: autoRefresh ? refreshInterval : undefined,
  });

  const handleAutoRefreshChange = (checked: boolean) => {
    setAutoRefresh(checked);
  };

  const handleIntervalChange = (value: string) => {
    setRefreshInterval(Number(value));
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Queue Status" description="Loading queue status..."></CardHeader>
        <CardBody>
          <div className="text-center py-8">Loading queue status...</div>
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Queue Status" description="Error loading queue status"></CardHeader>
        <CardBody>
          <div className="text-center py-8 text-destructive">
            Error loading queue status: {error.message}
            <Button variant="outline" className="mt-4" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        </CardBody>
      </Card>
    );
  }

  const orgQueues = queueStatus?.organization_queues || [];
  const totalQueued = queueStatus?.total_queued || 0;
  const totalRunning = queueStatus?.total_running || 0;
  const totalPending = queueStatus?.total_pending || 0;
  const maxPendingPerOrg = queueStatus?.max_pending_per_org || 500;

  return (
    <Card>
      <CardHeader
        title="Queue Status"
        description="Real-time queue metrics and organization-level breakdown"
        actions={
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => handleAutoRefreshChange(e.target.checked)}
              />
              Auto-refresh ({refreshInterval / 1000}s)
            </label>
            <select
              className="px-2 py-1 border rounded text-sm"
              value={refreshInterval}
              onChange={(e) => handleIntervalChange(e.target.value)}
              disabled={!autoRefresh}
            >
              <option value="5000">5s</option>
              <option value="15000">15s</option>
              <option value="30000">30s</option>
              <option value="60000">60s</option>
            </select>
          </div>
        }
      ></CardHeader>
      <CardBody className="space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardBody className="p-4">
              <div className="text-sm text-muted-foreground">Total Queued</div>
              <div className="text-3xl font-bold">{totalQueued}</div>
            </CardBody>
          </Card>

          <Card>
            <CardBody className="p-4">
              <div className="text-sm text-muted-foreground">Running</div>
              <div className="text-3xl font-bold">{totalRunning}</div>
            </CardBody>
          </Card>

          <Card>
            <CardBody className="p-4">
              <div className="text-sm text-muted-foreground">Pending (Queued + Running)</div>
              <div className="text-3xl font-bold">{totalPending}</div>
            </CardBody>
          </Card>

          <Card>
            <CardBody className="p-4">
              <div className="text-sm text-muted-foreground">Max Per Org</div>
              <div className="text-3xl font-bold">{maxPendingPerOrg}</div>
            </CardBody>
          </Card>
        </div>

        {/* Organization Queues Table */}
        <div>
          <h4 className="text-lg font-semibold mb-4">Organization Queues</h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Organization</TableHead>
                <TableHead>Queued</TableHead>
                <TableHead>Running</TableHead>
                <TableHead>Pending</TableHead>
                <TableHead>Utilization</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orgQueues.length > 0 ? (
                orgQueues.map((org) => (
                  <TableRow key={org.organization_id}>
                    <TableCell className="font-medium">{org.organization_name}</TableCell>
                    <TableCell>{org.queued_count}</TableCell>
                    <TableCell>{org.running_count}</TableCell>
                    <TableCell>{org.pending_count}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary"
                            style={{
                              width: `${Math.min(100, (org.pending_count / maxPendingPerOrg) * 100)}%`,
                            }}
                          />
                        </div>
                        <span className="text-sm font-mono">
                          {Math.round((org.pending_count / maxPendingPerOrg) * 100)}%
                        </span>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                    No organization queue data available.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardBody>
    </Card>
  );
}
