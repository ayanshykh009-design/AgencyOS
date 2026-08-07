"use client";

// Additional monitoring components for Item 9 - Execution statistics display.
//
// Provides detailed execution statistics display with filtering and visualization.
// Part of the operational monitoring components for production visibility.
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

import { useExecutionStatistics } from "@/services/monitoring";

/**
 * Execution statistics display component.
 * Shows execution counts by status and workflow distribution with filtering.
 */
export function ExecutionStatisticsDisplay() {
  const [hours, setHours] = useState<number>(24);

  const { data: executionStats, isLoading, error } = useExecutionStatistics(hours);

  const handleHoursChange = (value: string) => {
    setHours(Number(value));
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader
          title="Execution Statistics"
          description="Loading execution statistics..."
        ></CardHeader>
        <CardBody>
          <div className="text-center py-8">Loading execution statistics...</div>
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader
          title="Execution Statistics"
          description="Error loading statistics"
        ></CardHeader>
        <CardBody>
          <div className="text-center py-8 text-destructive">
            Error loading execution statistics: {error.message}
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Execution Statistics"
        description="Execution counts by status and workflow distribution"
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

        {/* Statistics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-2">
            <h4 className="text-lg font-semibold">Status Distribution</h4>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Count</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(executionStats?.counts_by_status || {}).map(([status, count]) => (
                  <TableRow key={status}>
                    <TableCell className="capitalize font-medium">{status}</TableCell>
                    <TableCell>{count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="space-y-2">
            <h4 className="text-lg font-semibold">Summary</h4>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Total Executions:</span>
                <span className="font-semibold">{executionStats?.total_executions}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Queued:</span>
                <span className="font-semibold">
                  {executionStats?.counts_by_status.queued || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Running:</span>
                <span className="font-semibold">
                  {executionStats?.counts_by_status.running || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Completed:</span>
                <span className="font-semibold">
                  {executionStats?.counts_by_status.succeeded || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Failed:</span>
                <span className="font-semibold">
                  {executionStats?.counts_by_status.failed || 0}
                </span>
              </div>
            </div>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
