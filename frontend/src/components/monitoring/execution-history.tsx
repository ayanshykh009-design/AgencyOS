"use client";

// Execution History component for Item 9.
//
// Provides detailed execution history with pagination, filtering, and export capabilities.
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
import { Input } from "@/components/ui/input";

import { useExecutionHistory } from "@/services/monitoring";
import type { ExecutionHistoryEntry } from "@/types/monitoring";

/**
 * Execution history display component.
 * Shows paginated execution history with filtering, sorting, and export.
 */
export function ExecutionHistoryDisplay() {
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);
  const [hours, setHours] = useState<number>(168); // Default 1 week
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [workflowFilter, setWorkflowFilter] = useState<string>("");

  const {
    data: historyData,
    isLoading,
    error,
  } = useExecutionHistory({
    page,
    page_size: pageSize,
    hours,
    status: statusFilter !== "all" ? statusFilter : undefined,
    workflow: workflowFilter || undefined,
  });

  const handleHoursChange = (value: string) => {
    setHours(Number(value));
    setPage(1);
  };

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setPage(1);
  };

  const handleWorkflowChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setWorkflowFilter(event.target.value);
    setPage(1);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
  };

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize);
    setPage(1);
  };

  const handleExport = async () => {
    // Implementation for CSV export
    const exportUrl = `/monitoring/execution-history/export?hours=${hours}&status=${statusFilter}&workflow=${workflowFilter}`;
    window.open(exportUrl, "_blank");
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader
          title="Execution History"
          description="Loading execution history..."
        ></CardHeader>
        <CardBody>
          <div className="text-center py-8">Loading execution history...</div>
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Execution History" description="Error loading history"></CardHeader>
        <CardBody>
          <div className="text-center py-8 text-destructive">
            Error loading execution history: {error.message}
          </div>
        </CardBody>
      </Card>
    );
  }

  const entries = historyData?.entries || [];
  const total = historyData?.total || 0;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <Card>
      <CardHeader
        title="Execution History"
        description="Paginated execution history with filtering and export"
        actions={
          <Button variant="outline" onClick={handleExport} disabled={entries.length === 0}>
            Export CSV
          </Button>
        }
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
              <option value="24">Last 24 Hours</option>
              <option value="168">Last Week</option>
              <option value="720">Last Month</option>
              <option value="8760">Last Year</option>
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

        {/* History Table */}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Started</TableHead>
              <TableHead>Workflow</TableHead>
              <TableHead>Execution ID</TableHead>
              <TableHead>Trigger</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Requested By</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.length > 0 ? (
              entries.map((entry: ExecutionHistoryEntry) => (
                <TableRow key={entry.id}>
                  <TableCell className="font-mono text-sm">
                    {new Date(entry.started_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="font-medium">{entry.workflow_name}</TableCell>
                  <TableCell className="font-mono text-sm">
                    {entry.execution_id.slice(0, 8)}...
                  </TableCell>
                  <TableCell className="capitalize">{entry.trigger_type || "manual"}</TableCell>
                  <TableCell>
                    <Badge tone={getStatusBadgeTone(entry.status)}>{entry.status}</Badge>
                  </TableCell>
                  <TableCell>
                    {entry.duration_ms ? `${(entry.duration_ms / 1000).toFixed(2)}s` : "—"}
                  </TableCell>
                  <TableCell>{entry.requested_by || "System"}</TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                  No execution history entries found matching the current filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <div className="text-sm text-muted-foreground">
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total}{" "}
              entries
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handlePageChange(page - 1)}
                disabled={page === 1}
                className="px-2 py-1 text-sm border rounded disabled:opacity-50"
              >
                Previous
              </button>
              <span className="text-sm">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => handlePageChange(page + 1)}
                disabled={page === totalPages}
                className="px-2 py-1 text-sm border rounded disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}

        <div className="text-sm text-muted-foreground">
          Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total}{" "}
          entries
        </div>
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
