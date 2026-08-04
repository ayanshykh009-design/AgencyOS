// Workflow detail: status, definition, triggers, and recent executions.
"use client";

import { useCallback, useEffect, use, useState } from "react";

import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
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
import { ROUTES } from "@/lib/constants";
import {
  EXECUTION_STATUS_LABELS,
  TRIGGER_TYPE_LABELS,
  WORKFLOW_STATUS_LABELS,
  executionStatusTone,
  formatDateTime,
  workflowStatusTone,
} from "@/lib/format";
import { can } from "@/lib/permissions";
import {
  activateWorkflow,
  archiveWorkflow,
  deleteWorkflow,
  getWorkflow,
  pauseWorkflow,
  updateWorkflow,
} from "@/services/workflows";
import {
  createWorkflowTrigger,
  disableWorkflowTrigger,
  enableWorkflowTrigger,
  listWorkflowTriggers,
} from "@/services/workflow-triggers";
import { listWorkflowExecutions } from "@/services/workflow-executions";
import type { Workflow, WorkflowExecution, WorkflowTrigger, WorkflowTriggerType } from "@/types";

export default function WorkflowDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const session = useAuth();
  const { id: workflowId } = use(params);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [triggers, setTriggers] = useState<WorkflowTrigger[]>([]);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // Create-trigger modal state.
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [triggerName, setTriggerName] = useState("");
  const [triggerType, setTriggerType] = useState<WorkflowTriggerType>("event");
  const [triggerEventType, setTriggerEventType] = useState("");
  const [triggerCron, setTriggerCron] = useState("");
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([
      getWorkflow(workflowId),
      listWorkflowTriggers({ workflowId, limit: 200 }),
      listWorkflowExecutions({ workflowId, limit: 20 }),
    ])
      .then(([wf, triggerPage, execPage]) => {
        setWorkflow(wf);
        setTriggers(triggerPage.items);
        setExecutions(execPage.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load workflow");
      })
      .finally(() => setLoading(false));
  }, [workflowId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!session) return null;
  const canWrite = can(session.user.role, "automation_write");
  const canManage = can(session.user.role, "automation_manage");

  const transition = (fn: () => Promise<unknown>) => {
    setBusy(true);
    fn()
      .then(() => load())
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Action failed");
      })
      .finally(() => setBusy(false));
  };

  const toggleTrigger = (trigger: WorkflowTrigger) => {
    transition(() =>
      trigger.enabled ? disableWorkflowTrigger(trigger.id) : enableWorkflowTrigger(trigger.id)
    );
  };

  const handleDelete = () => {
    setBusy(true);
    deleteWorkflow(workflowId)
      .then(() => {
        window.location.href = ROUTES.workflows;
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to delete workflow");
        setDeleteOpen(false);
      })
      .finally(() => setBusy(false));
  };

  const handleCreateTrigger = () => {
    if (!triggerName.trim() || (triggerType === "event" && !triggerEventType.trim())) {
      setTriggerError("Name and event type are required");
      return;
    }
    setBusy(true);
    setTriggerError(null);
    createWorkflowTrigger({
      workflow_id: workflowId,
      name: triggerName.trim(),
      trigger_type: triggerType,
      event_type: triggerType === "event" ? triggerEventType.trim() : undefined,
      schedule_cron: triggerType === "schedule" ? triggerCron.trim() : undefined,
    })
      .then(() => {
        setTriggerOpen(false);
        setTriggerName("");
        setTriggerEventType("");
        setTriggerCron("");
        load();
      })
      .catch((err: unknown) => {
        setTriggerError(err instanceof ApiRequestError ? err.message : "Failed to create trigger");
      })
      .finally(() => setBusy(false));
  };

  if (loading) return <Spinner label="Loading workflow…" />;
  if (!workflow) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-red-600">{error ?? "Workflow not found"}</p>
        <a href={ROUTES.workflows} className="text-sm text-gray-500 hover:underline">
          ← Back to workflows
        </a>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={workflow.name}
        description={workflow.description ?? "No description"}
        actions={
          <>
            <a href={ROUTES.workflows} className="text-sm text-gray-500 hover:underline">
              ← Back
            </a>
            {canManage ? (
              <>
                {workflow.status === "draft" || workflow.status === "paused" ? (
                  <Button
                    disabled={busy}
                    onClick={() => transition(() => activateWorkflow(workflowId))}
                  >
                    Activate
                  </Button>
                ) : null}
                {workflow.status === "active" ? (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => transition(() => pauseWorkflow(workflowId))}
                  >
                    Pause
                  </Button>
                ) : null}
                {workflow.status !== "archived" ? (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => transition(() => archiveWorkflow(workflowId))}
                  >
                    Archive
                  </Button>
                ) : null}
                <Button variant="danger" disabled={busy} onClick={() => setDeleteOpen(true)}>
                  Delete
                </Button>
              </>
            ) : null}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
        <Badge tone={workflowStatusTone(workflow.status)}>{workflow.status}</Badge>
        <span>Mode: {workflow.execution_mode}</span>
        <span>Version: v{workflow.version}</span>
        <span>Updated: {formatDateTime(workflow.updated_at)}</span>
      </div>

      <Card>
        <CardHeader
          title="Triggers"
          actions={
            canWrite ? <Button onClick={() => setTriggerOpen(true)}>Add trigger</Button> : undefined
          }
        />
        <CardBody>
          {triggers.length === 0 ? (
            <EmptyState title="No triggers" description="Add a trigger to run this workflow." />
          ) : (
            <Table>
              <THead>
                <tr>
                  <TH>Name</TH>
                  <TH>Type</TH>
                  <TH>Condition</TH>
                  <TH>Status</TH>
                  <TH />
                </tr>
              </THead>
              <TBody>
                {triggers.map((trigger) => (
                  <TRow key={trigger.id}>
                    <TD className="font-medium text-gray-900">{trigger.name}</TD>
                    <TD className="text-gray-600">{TRIGGER_TYPE_LABELS[trigger.trigger_type]}</TD>
                    <TD className="text-gray-600">
                      {trigger.trigger_type === "event"
                        ? (trigger.event_type ?? "—")
                        : trigger.trigger_type === "schedule"
                          ? (trigger.schedule_cron ?? "—")
                          : "—"}
                    </TD>
                    <TD>
                      <Badge tone={trigger.enabled ? "green" : "gray"}>
                        {trigger.enabled ? "Enabled" : "Disabled"}
                      </Badge>
                    </TD>
                    <TD className="text-right">
                      {canWrite ? (
                        <Button variant="outline" onClick={() => toggleTrigger(trigger)}>
                          {trigger.enabled ? "Disable" : "Enable"}
                        </Button>
                      ) : null}
                    </TD>
                  </TRow>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Recent executions" />
        <CardBody>
          {executions.length === 0 ? (
            <EmptyState
              title="No executions"
              description="Executions will appear here when this workflow runs."
            />
          ) : (
            <Table>
              <THead>
                <tr>
                  <TH>Status</TH>
                  <TH>Attempts</TH>
                  <TH>Started</TH>
                  <TH>Finished</TH>
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
                    <TD className="text-gray-600">
                      {execution.attempts}/{execution.max_attempts}
                    </TD>
                    <TD className="text-xs text-gray-400">
                      {execution.started_at ? formatDateTime(execution.started_at) : "—"}
                    </TD>
                    <TD className="text-xs text-gray-400">
                      {execution.finished_at ? formatDateTime(execution.finished_at) : "—"}
                    </TD>
                  </TRow>
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      <Modal
        open={triggerOpen}
        title="Add trigger"
        onClose={() => setTriggerOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setTriggerOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={handleCreateTrigger} disabled={busy}>
              {busy ? "Creating…" : "Create"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Name" htmlFor="trig-name" required>
            <Input
              id="trig-name"
              value={triggerName}
              onChange={(e) => setTriggerName(e.target.value)}
              placeholder="e.g. On lead created"
            />
          </Field>
          <Field label="Trigger type" htmlFor="trig-type">
            <Select
              id="trig-type"
              value={triggerType}
              onChange={(e) => setTriggerType(e.target.value as WorkflowTriggerType)}
            >
              <option value="event">Event</option>
              <option value="schedule">Schedule</option>
              <option value="manual">Manual</option>
            </Select>
          </Field>
          {triggerType === "event" ? (
            <Field label="Event type" htmlFor="trig-event" required>
              <Input
                id="trig-event"
                value={triggerEventType}
                onChange={(e) => setTriggerEventType(e.target.value)}
                placeholder="e.g. lead_created"
              />
            </Field>
          ) : null}
          {triggerType === "schedule" ? (
            <Field label="Cron expression" htmlFor="trig-cron" hint="UTC, five-field cron">
              <Input
                id="trig-cron"
                value={triggerCron}
                onChange={(e) => setTriggerCron(e.target.value)}
                placeholder="e.g. 0 9 * * 1"
              />
            </Field>
          ) : null}
          {triggerError ? <p className="text-sm text-red-600">{triggerError}</p> : null}
        </div>
      </Modal>

      <ConfirmDialog
        open={deleteOpen}
        title="Delete workflow"
        message={`Delete "${workflow.name}"? This only works for draft or archived workflows.`}
        confirmLabel="Delete"
        busy={busy}
        onClose={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
