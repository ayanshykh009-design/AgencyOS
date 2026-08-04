// Executions: history and manual control of workflow runs.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
  EmptyState,
  PageHeader,
  Select,
  Spinner,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TRow,
} from "@/components/ui";
import { useAuth } from "@/hooks/use-auth";
import { ApiRequestError } from "@/lib/api-client";
import { EXECUTION_STATUS_LABELS, executionStatusTone, formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import {
  cancelWorkflowExecution,
  listWorkflowExecutions,
  retryWorkflowExecution,
} from "@/services/workflow-executions";
import type { ExecutionStatus, WorkflowExecution } from "@/types";

const STATUS_OPTIONS: Array<{ value: ExecutionStatus; label: string }> = Object.entries(
  EXECUTION_STATUS_LABELS
).map(([value, label]) => ({ value: value as ExecutionStatus, label }));

export default function ExecutionsPage() {
  const session = useAuth();
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback((filter: string) => {
    listWorkflowExecutions({
      status: (filter || undefined) as ExecutionStatus | undefined,
      limit: 200,
    })
      .then((page) => {
        setExecutions(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load executions");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(statusFilter);
  }, [load, statusFilter]);

  if (!session) return null;
  const canWrite = can(session.user.role, "automation_write");

  const runAction = (id: string, fn: (id: string) => Promise<WorkflowExecution>) => {
    setBusyId(id);
    fn(id)
      .then(() => load(statusFilter))
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Action failed");
      })
      .finally(() => setBusyId(null));
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Executions"
        description="Run history for every workflow in the organization."
        actions={
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-48"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        }
      />

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading executions…" />
      ) : executions.length === 0 ? (
        <EmptyState
          title="No executions"
          description="Runs will appear here as workflows execute."
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Status</TH>
              <TH>Workflow</TH>
              <TH>Attempts</TH>
              <TH>Started</TH>
              <TH>Finished</TH>
              <TH />
            </tr>
          </THead>
          <TBody>
            {executions.map((execution) => (
              <TRow key={execution.id}>
                <TD>
                  <Badge tone={executionStatusTone(execution.status)}>
                    {EXECUTION_STATUS_LABELS[execution.status]}
                  </Badge>
                </TD>
                <TD className="font-mono text-xs text-gray-600">
                  {execution.workflow_id.slice(0, 8)}
                </TD>
                <TD className="text-gray-600">
                  {execution.attempts}/{execution.max_attempts}
                </TD>
                <TD className="text-xs text-gray-400">
                  {execution.started_at ? formatDateTime(execution.started_at) : "—"}
                </TD>
                <TD className="text-xs text-gray-400">
                  {execution.finished_at ? formatDateTime(execution.finished_at) : "—"}
                </TD>
                <TD className="text-right">
                  {canWrite ? (
                    <div className="flex items-center justify-end gap-2">
                      {(execution.status === "failed" || execution.status === "retrying") && (
                        <Button
                          variant="outline"
                          disabled={busyId === execution.id}
                          onClick={() => runAction(execution.id, retryWorkflowExecution)}
                        >
                          Retry
                        </Button>
                      )}
                      {(execution.status === "queued" ||
                        execution.status === "running" ||
                        execution.status === "retrying") && (
                        <Button
                          variant="ghost"
                          disabled={busyId === execution.id}
                          onClick={() => runAction(execution.id, cancelWorkflowExecution)}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  ) : null}
                </TD>
              </TRow>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
