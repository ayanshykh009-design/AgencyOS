// Executions: read-only history with summary counts, sanitized error summary,
// a technical event timeline, and state-dependent write actions.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  AutomationListState,
  DisabledActionReason,
  RedactedMetadata,
  actionDisabledReason,
  formatUtcOrNever,
  redactMetadata,
} from "@/components/automation/automation-states";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Modal,
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
import { EXECUTION_STATUS_LABELS, executionStatusTone } from "@/lib/format";
import {
  canCancelExecution,
  canQueueExecution,
  canReadExecutions,
  canRetryExecution,
  canStartExecution,
} from "@/lib/batch6-permissions";
import {
  cancelWorkflowExecution,
  getWorkflowExecution,
  listExecutionEvents,
  listWorkflowExecutions,
  queueWorkflowExecution,
  retryWorkflowExecution,
  startWorkflowExecution,
} from "@/services/workflow-executions";
import type {
  ExecutionStatus,
  UserRole,
  WorkflowExecution,
  WorkflowExecutionEvent,
  WorkflowExecutionQueue,
} from "@/types";

const STATUS_OPTIONS: Array<{ value: ExecutionStatus; label: string }> = Object.entries(
  EXECUTION_STATUS_LABELS
).map(([value, label]) => ({ value: value as ExecutionStatus, label }));

const EVENT_TYPE_LABELS: Record<WorkflowExecutionEvent["event_type"], string> = {
  queued: "Queued",
  started: "Started",
  adapter_dispatched: "Adapter dispatched",
  adapter_returned: "Adapter returned",
  step_started: "Step started",
  step_completed: "Step completed",
  step_failed: "Step failed",
  retrying: "Retrying",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
  timeout_guard: "Timeout guard",
};

export function executionErrorMessage(err: unknown): string {
  return err instanceof ApiRequestError ? err.message : "Failed to load executions";
}

/** UTC-safe derived duration; unfinished or invalid runs stay explicitly unavailable. */
export function formatExecutionDuration(
  startedAt: string | null,
  finishedAt: string | null
): string {
  if (!startedAt || !finishedAt) return "—";
  const start = Date.parse(startedAt);
  const end = Date.parse(finishedAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "—";
  const totalSeconds = Math.round((end - start) / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return `${minutes}m ${seconds}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/** Sanitized read of backend `execution.error`: allowlisted keys only. */
export function ExecutionErrorSummary({ error }: { error: Record<string, unknown> | null }) {
  const rows = Object.entries(redactMetadata(error));
  if (rows.length === 0) return null;
  return (
    <div data-testid="execution-error-summary" className="mt-2 rounded-md bg-red-50 px-3 py-2">
      <p className="text-xs font-medium text-red-800">Error summary (redacted)</p>
      <RedactedMetadata metadata={error} />
    </div>
  );
}

interface ExecutionRowActionsProps {
  role: UserRole;
  status: ExecutionStatus;
  busy: boolean;
  onStart: () => void;
  onRetry: () => void;
  onCancel: () => void;
  onDetails: () => void;
}

/** Exported for static-markup tests: writes require workflow_write + state. */
export function ExecutionRowActions({
  role,
  status,
  busy,
  onStart,
  onRetry,
  onCancel,
  onDetails,
}: ExecutionRowActionsProps) {
  const mayWrite = canQueueExecution(role);
  const startReason = actionDisabledReason(
    status === "queued",
    "Only queued executions can be started."
  );
  const retryReason = actionDisabledReason(
    status === "failed" || status === "timed_out" || status === "retrying",
    "Only failed, timed out or retrying executions can be retried."
  );
  const cancelReason = actionDisabledReason(
    status === "queued" || status === "running" || status === "retrying",
    "Only non-terminal executions can be cancelled."
  );

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button variant="ghost" onClick={onDetails}>
        Details
      </Button>
      {mayWrite && canStartExecution(role) ? (
        <Button
          variant="outline"
          disabled={busy || startReason !== null}
          title={startReason ?? undefined}
          onClick={onStart}
        >
          Start
        </Button>
      ) : null}
      {mayWrite && canRetryExecution(role) ? (
        <Button
          variant="outline"
          disabled={busy || retryReason !== null}
          title={retryReason ?? undefined}
          onClick={onRetry}
        >
          Retry
        </Button>
      ) : null}
      {mayWrite && canCancelExecution(role) ? (
        <Button
          variant="ghost"
          disabled={busy || cancelReason !== null}
          title={cancelReason ?? undefined}
          onClick={onCancel}
        >
          Cancel
        </Button>
      ) : null}
      {busy ? <DisabledActionReason reason="An action is in progress." /> : null}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <Card className="min-w-[8rem] flex-1">
      <CardBody>
        <p className="text-xs uppercase tracking-wide text-gray-500">{label}</p>
        <p className="mt-1 text-xl font-semibold text-gray-900">{value}</p>
      </CardBody>
    </Card>
  );
}

export default function ExecutionsPage() {
  const session = useAuth();
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<{
    execution: WorkflowExecution | null;
    events: WorkflowExecutionEvent[];
    loading: boolean;
    error: string | null;
  } | null>(null);
  const [queueResult, setQueueResult] = useState<WorkflowExecutionQueue | null>(null);

  const fetchExecutions = useCallback((filter: string) => {
    return listWorkflowExecutions({
      status: (filter || undefined) as ExecutionStatus | undefined,
      limit: 200,
    })
      .then((page) => {
        setExecutions(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setExecutions([]);
        setError(executionErrorMessage(err));
      })
      .finally(() => setLoading(false));
  }, []);

  const reload = useCallback(
    (filter: string) => {
      setLoading(true);
      return fetchExecutions(filter);
    },
    [fetchExecutions]
  );

  useEffect(() => {
    if (session) void fetchExecutions(statusFilter);
  }, [fetchExecutions, session, statusFilter]);

  if (!session) return null;
  const role = session.user.role;
  const canRead = canReadExecutions(role);
  const canWrite = canQueueExecution(role);

  const counts = {
    total: executions.length,
    queued: executions.filter((e) => e.status === "queued").length,
    running: executions.filter((e) => e.status === "running").length,
    succeeded: executions.filter((e) => e.status === "succeeded").length,
    failed: executions.filter((e) => e.status === "failed" || e.status === "timed_out").length,
  };

  const runAction = (id: string, fn: (id: string) => Promise<WorkflowExecution>) => {
    setBusyId(id);
    fn(id)
      .then(() => {
        setError(null);
        return reload(statusFilter);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Action failed");
      })
      .finally(() => setBusyId(null));
  };

  const openDetail = (id: string) => {
    setDetailId(id);
    setQueueResult(null);
    setDetail({ execution: null, events: [], loading: true, error: null });
    Promise.all([getWorkflowExecution(id), listExecutionEvents(id, { limit: 100 })])
      .then(([execution, page]) => {
        setDetail({ execution, events: page.items, loading: false, error: null });
      })
      .catch((err: unknown) => {
        setDetail({
          execution: null,
          events: [],
          loading: false,
          error: err instanceof ApiRequestError ? err.message : "Failed to load execution detail",
        });
      });
  };

  const queueAnother = () => {
    const workflowId = detail?.execution?.workflow_id;
    if (!workflowId) return;
    setBusyId(workflowId);
    setQueueResult(null);
    queueWorkflowExecution({ workflow_id: workflowId })
      .then((result) => {
        setQueueResult(result);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to queue execution");
      })
      .finally(() => setBusyId(null));
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Executions"
        description="Workflow run history for the organization. Actions depend on the run state."
        actions={
          canRead ? (
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-48"
              aria-label="Filter by status"
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          ) : undefined
        }
      />

      <AutomationListState
        denied={!canRead}
        deniedMessage="You do not have permission to view workflow executions."
        loading={loading}
        loadingLabel="Loading executions…"
        error={error}
        onRetry={() => void reload(statusFilter)}
        empty={executions.length === 0}
        emptyTitle="No executions"
        emptyDescription="Runs will appear here as workflows execute."
      />

      {canRead && !loading && !error && executions.length > 0 ? (
        <>
          <div>
            <p className="mb-2 text-xs text-gray-500">Counts across the loaded executions</p>
            <div className="flex flex-wrap gap-3">
              <SummaryCard label="Loaded" value={counts.total} />
              <SummaryCard label="Queued" value={counts.queued} />
              <SummaryCard label="Running" value={counts.running} />
              <SummaryCard label="Succeeded" value={counts.succeeded} />
              <SummaryCard label="Failed" value={counts.failed} />
            </div>
          </div>

          <Table>
            <THead>
              <tr>
                <TH>Status</TH>
                <TH>Workflow</TH>
                <TH>Attempts</TH>
                <TH>Started (UTC)</TH>
                <TH>Finished (UTC)</TH>
                <TH>Duration</TH>
                <TH>Actions</TH>
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
                  <TD className="text-xs text-gray-600">
                    {formatUtcOrNever(execution.started_at)}
                  </TD>
                  <TD className="text-xs text-gray-600">
                    {formatUtcOrNever(execution.finished_at)}
                  </TD>
                  <TD className="text-xs text-gray-600">
                    {formatExecutionDuration(execution.started_at, execution.finished_at)}
                  </TD>
                  <TD>
                    <ExecutionRowActions
                      role={role}
                      status={execution.status}
                      busy={busyId === execution.id}
                      onStart={() => runAction(execution.id, startWorkflowExecution)}
                      onRetry={() => runAction(execution.id, retryWorkflowExecution)}
                      onCancel={() => runAction(execution.id, cancelWorkflowExecution)}
                      onDetails={() => openDetail(execution.id)}
                    />
                  </TD>
                </TRow>
              ))}
            </TBody>
          </Table>
        </>
      ) : null}

      <Modal
        open={detailId !== null}
        title="Execution detail"
        onClose={() => {
          setDetailId(null);
          setDetail(null);
        }}
        width="lg"
      >
        {detail?.loading ? (
          <Spinner label="Loading execution detail…" />
        ) : detail?.error ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-red-700">{detail.error}</p>
            <Button variant="outline" onClick={() => detailId && openDetail(detailId)}>
              Retry
            </Button>
          </div>
        ) : detail?.execution ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
              <Badge tone={executionStatusTone(detail.execution.status)}>
                {EXECUTION_STATUS_LABELS[detail.execution.status]}
              </Badge>
              <span className="font-mono text-xs">{detail.execution.id}</span>
              <span>Workflow: {detail.execution.workflow_id.slice(0, 8)}</span>
              <span>
                Attempts: {detail.execution.attempts}/{detail.execution.max_attempts}
              </span>
            </div>

            <ExecutionErrorSummary error={detail.execution.error} />

            {canWrite ? (
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" disabled={busyId !== null} onClick={queueAnother}>
                  Queue another run
                </Button>
                <DisabledActionReason reason="Uses the existing queue endpoint; no code is executed here." />
              </div>
            ) : null}
            {queueResult ? (
              <p role="status" data-state="queue-result" className="text-sm text-green-800">
                Queued execution <span className="font-mono">{queueResult.execution_id}</span> with
                status <span className="font-mono">{queueResult.status}</span>.
              </p>
            ) : null}

            <div>
              <h4 className="text-sm font-semibold">Technical timeline</h4>
              {detail.events.length === 0 ? (
                <EmptyState title="No events" description="No technical events recorded yet." />
              ) : (
                <ol className="mt-2 flex flex-col gap-3">
                  {detail.events.map((event) => (
                    <li key={event.id} className="rounded-md border px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-medium">
                          {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
                        </p>
                        <p className="text-xs text-gray-600">
                          Attempt {event.attempt} · {formatUtcOrNever(event.occurred_at)}
                        </p>
                      </div>
                      <RedactedMetadata metadata={event.metadata} />
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        ) : (
          <EmptyState title="Execution unavailable" description="No detail was returned." />
        )}
      </Modal>
    </div>
  );
}
