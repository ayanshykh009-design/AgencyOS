"use client";

// Monitoring Information component for Item 9.
//
// Displays comprehensive system monitoring information including system health,
// resource usage, and operational metrics.
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

import { useMonitoringInformation } from "@/services/monitoring";
import type { MonitoringInformationResponse } from "@/types/monitoring";

/**
 * Monitoring information display component.
 * Shows comprehensive system monitoring data including health, resources, and operational metrics.
 */
export function MonitoringInformationDisplay() {
  const { data: monitoringInfo, isLoading, error } = useMonitoringInformation();

  if (isLoading) {
    return (
      <Card>
        <CardHeader
          title="Monitoring Information"
          description="Loading system monitoring data..."
        ></CardHeader>
        <CardBody>
          <div className="text-center py-8">Loading monitoring information...</div>
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader
          title="Monitoring Information"
          description="Error loading monitoring data"
        ></CardHeader>
        <CardBody>
          <div className="text-center py-8 text-destructive">
            Error loading monitoring information: {error.message}
          </div>
        </CardBody>
      </Card>
    );
  }

  if (!monitoringInfo) {
    return (
      <Card>
        <CardHeader
          title="Monitoring Information"
          description="No monitoring data available"
        ></CardHeader>
        <CardBody>
          <div className="text-center py-8 text-muted-foreground">
            No monitoring information available.
          </div>
        </CardBody>
      </Card>
    );
  }

  const system = monitoringInfo.system;
  const database = monitoringInfo.database;
  const workers = monitoringInfo.workers;
  const queue = monitoringInfo.queue;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Monitoring Information</CardTitle>
        <CardDescription>Comprehensive system health and operational metrics</CardDescription>
      </CardHeader>
      <CardBody className="space-y-6">
        {/* System Health */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>System Health</CardTitle>
              <CardDescription>Overall system status</CardDescription>
            </CardHeader>
            <CardBody className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status:</span>
                <Badge tone={system.healthy ? "green" : "red"}>
                  {system.healthy ? "Healthy" : "Degraded"}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Uptime:</span>
                <span className="font-mono">{system.uptime}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Version:</span>
                <span className="font-mono">{system.version}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Environment:</span>
                <span className="font-mono">{system.environment}</span>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Database</CardTitle>
              <CardDescription>Database connection and performance</CardDescription>
            </CardHeader>
            <CardBody className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status:</span>
                <Badge tone={database.connected ? "green" : "red"}>
                  {database.connected ? "Connected" : "Disconnected"}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Pool Usage:</span>
                <span className="font-mono">{database.pool_usage}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Active Connections:</span>
                <span className="font-mono">{database.active_connections}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Avg Query Time:</span>
                <span className="font-mono">{database.avg_query_time}ms</span>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Workers</CardTitle>
              <CardDescription>Worker process status</CardDescription>
            </CardHeader>
            <CardBody className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Total Workers:</span>
                <span className="font-bold">{workers.total}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Healthy:</span>
                <Badge tone="green">{workers.healthy}</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Unhealthy:</span>
                <Badge tone="red">{workers.unhealthy}</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Last Heartbeat:</span>
                <span className="font-mono">{workers.last_heartbeat}</span>
              </div>
            </CardBody>
          </Card>
        </div>

        {/* Resource Usage */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Resource Usage</CardTitle>
              <CardDescription>Current system resource consumption</CardDescription>
            </CardHeader>
            <CardBody className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">CPU Usage:</span>
                <span className="font-bold">{system.cpu_usage}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Memory Usage:</span>
                <span className="font-bold">{system.memory_usage}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Disk Usage:</span>
                <span className="font-bold">{system.disk_usage}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Network I/O:</span>
                <span className="font-mono">{system.network_io}</span>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Queue Metrics</CardTitle>
              <CardDescription>Current queue processing metrics</CardDescription>
            </CardHeader>
            <CardBody className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Total Queued:</span>
                <span className="font-bold">{queue.total_queued}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Running:</span>
                <span className="font-bold">{queue.running}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Completed (24h):</span>
                <span className="font-bold">{queue.completed_24h}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Failed (24h):</span>
                <span className="font-bold">{queue.failed_24h}</span>
              </div>
            </CardBody>
          </Card>
        </div>

        {/* Configuration */}
        <Card>
          <CardHeader>
            <CardTitle>Automation Configuration</CardTitle>
            <CardDescription>Current automation system configuration</CardDescription>
          </CardHeader>
          <CardBody>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Setting</TableHead>
                  <TableHead>Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell>Max Pending Per Org</TableCell>
                  <TableCell className="font-mono">{system.max_pending_per_org}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Execution Timeout</TableCell>
                  <TableCell className="font-mono">{system.execution_timeout}s</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Batch Size</TableCell>
                  <TableCell className="font-mono">{system.batch_size}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Poll Interval</TableCell>
                  <TableCell className="font-mono">{system.poll_interval}s</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Retention Enabled</TableCell>
                  <TableCell>
                    <Badge tone={system.retention_enabled ? "green" : "gray"}>
                      {system.retention_enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Retention Days</TableCell>
                  <TableCell className="font-mono">{system.retention_days}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardBody>
        </Card>
      </CardBody>
    </Card>
  );
}
