"use client";

// Execution Timeline component for Item 9.
//
// Displays a chronological timeline of execution events with filtering and detail views.
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
import { Input } from "@/components/ui/input";

import { useExecutionTimeline } from "@/services/monitoring";
import type { ExecutionTimelineEvent } from "@/types/monitoring";

/**
 * Execution timeline display component.
 * Shows chronological execution events with filtering by status, workflow, and time range.
 */
export function ExecutionTimelineDisplay() {
  const [hours, setHours] = useState<number>(24);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [workflowFilter, setWorkflowFilter] = useState<string>("");

  const {
    data: timelineData,
    isLoading,
    error,
  } = useExecutionTimeline({
    hours,
    status: statusFilter !== "all" ? statusFilter : undefined,
    workflow: workflowFilter || undefined,
  });

  const handleHoursChange = (value: string) => {
    setHours(Number(value));
  };

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
  };

  const handleWorkflowChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setWorkflowFilter(event.target.value);
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Execution Timeline" description="Loading timeline data..."></CardHeader>
        <CardBody>
          <div className="text-center py-8">Loading execution timeline...</div>
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Execution Timeline" description="Error loading timeline"></CardHeader>
        <CardBody>
          <div className="text-center py-8 text-destructive">
            Error loading execution timeline: {error.message}
          </div>
        </CardBody>
      </Card>
    );
  }

  const events = timelineData?.events || [];

  return (
    <Card>
      <CardHeader
        title="Execution Timeline (Last {hours} Hours)"
        description="Chronological view of execution events"
      ></CardHeader>
      <CardBody className="space-y-6">
        {/* Controls */}
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Time Window</label>
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

          <div className="space-y-2 flex-1">
            <label className="text-sm font-medium">Status Filter</label>
            <select
              className="px-3 py-1 border rounded-md text-sm"
              value={statusFilter}
              onChange={(e) => handleStatusChange(e.target.value)}
            >
              <option value="all">All Statuses</option>
              <option value="queued">Queued</option>
              <option value="running">Running</option>
              <option value="succeeded">Succeeded</option>
              <option value="failed">Failed</option>
              <option value="retrying">Retrying</option>
              <option value="cancelled">Cancelled</option>
              <option value="timed_out">Timed Out</option>
            </select>
          </div>

          <div className="space-y-2 flex-1">
            <label className="text-sm font-medium">Workflow Filter</label>
            <Input
              value={workflowFilter}
              onChange={handleWorkflowChange}
              placeholder="Filter by workflow name..."
            />
          </div>
        </div>

        {/* Timeline Table */}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Workflow</TableHead>
              <TableHead>Execution ID</TableHead>
              <TableHead>Event</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Duration</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.length > 0 ? (
              events.map((event: ExecutionTimelineEvent) => (
                <TableRow key={event.id}>
                  <TableCell className="font-mono text-sm">
                    {new Date(event.timestamp).toLocaleString()}
                  </TableCell>
                  <TableCell className="font-medium">{event.workflow_name}</TableCell>
                  <TableCell className="font-mono text-sm">
                    {event.execution_id.slice(0, 8)}...
                  </TableCell>
                  <TableCell className="capitalize">
                    {event.event_type.replace(/_/g, " ")}
                  </TableCell>
                  <TableCell>
                    <Badge tone={getStatusBadgeTone(event.status)}>{event.status}</Badge>
                  </TableCell>
                  <TableCell>
                    {event.duration_ms ? `${(event.duration_ms / 1000).toFixed(2)}s` : "—"}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                  No execution events found matching the current filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>

        {events.length === 0 && !isLoading && (
          <div className="text-center py-8 text-muted-foreground">
            No execution events found for the selected time window and filters.
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function getStatusBadgeTone(status: string): "green" | "red" | "gray" | "amber" {
  switch (status) {
    case "succeeded":
      return "green";
    case "failed":
    case "timed_out":
      return "red";
    case "running":
    case "retrying":
      return "amber";
    case "queued":
    case "cancelled":
      return "gray";
    default:
      return "gray";
  }
}
