"use client";

// Worker statistics display component for Item 9.
//
// Provides comprehensive worker monitoring with health status, error distribution,
// and detailed worker information display.
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useWorkerStatistics } from "@/services/monitoring";

/**
 * Worker statistics display component.
 * Shows worker health status, error distribution, and individual worker details.
 */
export function WorkerStatisticsDisplay() {
  const [hours, setHours] = useState<number>(24);

  const { data: workerStats, isLoading, error } = useWorkerStatistics(hours);

  const handleHoursChange = (value: string) => {
    setHours(Number(value));
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader
          title="Worker Statistics"
          description="Loading worker statistics..."
        ></CardHeader>
        <CardBody>
          <div className="text-center py-8">Loading worker statistics...</div>
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Worker Statistics" description="Error loading statistics"></CardHeader>
        <CardBody>
          <div className="text-center py-8 text-destructive">
            Error loading worker statistics: {error.message}
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Worker Statistics"
        description="Worker health status, error distribution, and detailed worker information"
      ></CardHeader>
      <CardBody className="space-y-6">
        {/* Controls */}
        <div className="flex items-center space-x-4 mb-6">
          <div className="text-sm font-medium">Time Window:</div>
          <select
            className="px-3 py-1 border rounded-md text-sm"
            value={hours}
            onChange={(e) => handleHoursChange(e.target.value)}
          >
            <option value="1">Last Hour</option>
            <option value="6">Last 6 Hours</option>
            <option value="24">Last 24 Hours</option>
            <option value="72">Last 3 Days</option>
            <option value="168">Last Week</option>
          </select>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardBody className="p-4">
              <div className="text-sm text-muted-foreground">Active Workers</div>
              <div className="text-2xl font-bold">{workerStats?.active_workers}</div>
            </CardBody>
          </Card>

          <Card>
            <CardBody className="p-4">
              <div className="text-sm text-muted-foreground">Healthy Loops</div>
              <div className="text-2xl font-bold">{workerStats?.healthy_loops}</div>
            </CardBody>
          </Card>

          <Card>
            <CardBody className="p-4">
              <div className="text-sm text-muted-foreground">Errored Loops</div>
              <div className="text-2xl font-bold">{workerStats?.errored_loops}</div>
            </CardBody>
          </Card>

          <Card>
            <CardBody className="p-4">
              <div className="text-sm text-muted-foreground">Health Percentage</div>
              <div className="text-2xl font-bold">
                {workerStats?.health_percentage?.toFixed(1) || 0}%
              </div>
            </CardBody>
          </Card>
        </div>

        {/* Error Types */}
        {Object.keys(workerStats?.errors_by_type || {}).length > 0 && (
          <div className="mt-6">
            <h4 className="text-lg font-semibold mb-4">Error Types</h4>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Error Type</TableHead>
                  <TableHead>Count</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(workerStats?.errors_by_type || {})
                  .slice(0, 5)
                  .map(([error, count]) => (
                    <TableRow key={error}>
                      <TableCell className="font-medium truncate max-w-xs" title={error}>
                        {error}
                      </TableCell>
                      <TableCell>
                        <Badge tone="red">{count}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Worker Details */}
        <div className="mt-8">
          <h4 className="text-lg font-semibold mb-4">Worker Details</h4>
          <div className="space-y-4">
            {workerStats?.workers?.slice(0, 10).map((worker) => (
              <div
                key={worker.instance_id}
                className="flex items-center justify-between p-4 border rounded-lg"
              >
                <div className="flex-1">
                  <div className="font-medium">{worker.instance_id.toString().slice(0, 8)}...</div>
                  <div className="text-sm text-muted-foreground">
                    {worker.hostname} (PID: {worker.pid})
                  </div>
                </div>
                <div className="text-right">
                  <Badge tone={worker.loop_ok ? "green" : "red"}>
                    {worker.loop_ok ? "Healthy" : "Error"}
                  </Badge>
                  <div className="text-xs text-muted-foreground mt-1">
                    Last heartbeat: {new Date(worker.last_heartbeat_at).toLocaleString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
