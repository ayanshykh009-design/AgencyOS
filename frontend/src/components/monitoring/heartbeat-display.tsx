"use client";

// Additional monitoring component files for Item 9 frontend implementation.
//
// This file contains the remaining monitoring components that were referenced
// in the Operational Monitoring Page.
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardBody } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useHeartbeatVisibility } from "@/services/monitoring";

/**
 * Heartbeat visibility display component.
 * Shows real-time worker heartbeat status for administrative monitoring.
 */
export function HeartbeatVisibilityDisplay() {
  const [workerType, setWorkerType] = useState<string>("");
  const [staleWithinSeconds, setStaleWithinSeconds] = useState<number>(300);
  const [limit, setLimit] = useState<number>(100);

  const {
    data: heartbeatData,
    isLoading,
    error,
  } = useHeartbeatVisibility({
    worker_type: workerType || undefined,
    stale_within_seconds: staleWithinSeconds,
    limit,
  });

  const handleWorkerTypeChange = (value: string) => {
    setWorkerType(value);
  };

  const handleStaleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setStaleWithinSeconds(Number(event.target.value));
  };

  const handleLimitChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setLimit(Number(event.target.value));
  };

  return (
    <Card>
      <CardHeader
        title="Worker Heartbeat Visibility"
        description="Real-time worker heartbeat status for operational monitoring"
      ></CardHeader>
      <CardBody className="space-y-6">
        {/* Filters */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label htmlFor="worker-type">Worker Type</Label>
            <select
              id="worker-type"
              className="w-full rounded-md border bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
              value={workerType}
              onChange={(e) => handleWorkerTypeChange(e.target.value)}
            >
              <option value="">All</option>
              <option value="execution">Execution</option>
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="stale-within">Stale Within (seconds)</Label>
            <Input
              id="stale-within"
              type="number"
              min="60"
              max="86400"
              value={staleWithinSeconds}
              onChange={handleStaleChange}
              placeholder="300"
            />
            <p className="text-xs text-muted-foreground">Workers not seen within this window</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="limit">Limit</Label>
            <Input
              id="limit"
              type="number"
              min="1"
              max="1000"
              value={limit}
              onChange={handleLimitChange}
              placeholder="100"
            />
            <p className="text-xs text-muted-foreground">Maximum results to display</p>
          </div>
        </div>

        {/* Results */}
        {isLoading && <div className="text-center py-8">Loading heartbeat data...</div>}

        {error && (
          <div className="text-center py-8 text-destructive">
            Error loading heartbeat data: {error.message}
          </div>
        )}

        {heartbeatData && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h4 className="text-lg font-semibold">Worker Instances</h4>
              <Badge tone="gray">{heartbeatData.length} workers found</Badge>
            </div>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Instance ID</TableHead>
                  <TableHead>Worker Type</TableHead>
                  <TableHead>Hostname</TableHead>
                  <TableHead>PID</TableHead>
                  <TableHead>Last Heartbeat</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {heartbeatData.map((worker) => (
                  <TableRow key={worker.instance_id}>
                    <TableCell className="font-mono text-sm">
                      {worker.instance_id.toString().slice(0, 8)}...
                    </TableCell>
                    <TableCell>
                      <Badge tone="gray">{worker.worker_type}</Badge>
                    </TableCell>
                    <TableCell>{worker.hostname}</TableCell>
                    <TableCell>{worker.pid}</TableCell>
                    <TableCell>{new Date(worker.last_heartbeat_at).toLocaleString()}</TableCell>
                    <TableCell>
                      <Badge tone={worker.loop_ok ? "green" : "red"}>
                        {worker.loop_ok ? "Healthy" : "Error"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {heartbeatData.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                No worker instances found matching the current filters.
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
