// Workflow detail: read-only definition/config visualization, triggers,
// executions, authorized lifecycle actions and a truthful "Run now" action.
// No builder and no arbitrary code execution.
"use client";

import { useCallback, useEffect, use, useState } from "react";

import {
  AutomationListState,
  DisabledActionReason,
  RedactedMetadata,
  REDACTED,
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
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
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
  workflowStatusTone,
} from "@/lib/format";
import {
  canEditWorkflow,
  canManageWorkflowLifecycle,
  canQueueExecution,
  canReadWorkflows,
  canWriteTriggers,
} from "@/lib/batch6-permissions";
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
  updateWorkflowTrigger,
} from "@/services/workflow-triggers";
import { listWorkflowExecutions, queueWorkflowExecution } from "@/services/workflow-executions";
import type {
  UserRole,
  Workflow,
  WorkflowExecution,
  WorkflowExecutionQueue,
  WorkflowStatus,
  WorkflowTrigger,
  WorkflowTriggerType,
} from "@/types";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** Read-only visualization of the stored definition and config. */
export function WorkflowDefinitionView({
  definition,
  config,
}: {
  definition: Record<string, unknown>;
  config: Record<string, unknown>;
}) {
  const rawSteps = definition.steps;
  const steps = Array.isArray(rawSteps) ? rawSteps : [];
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          title="Definition"
          description="Read-only view of the stored definition. No steps can be added or executed here."
        />
        <CardBody>
          {steps.length > 0 ? (
            <ol className="flex flex-col gap-3">
              {steps.map((step, index) => (
                <li key={index} className="rounded-md border px-3 py-2">
                  <p className="text-xs font-medium text-gray-500">Step {index + 1}</p>
                  <RedactedMetadata metadata={asRecord(step)} />
                </li>
              ))}
            </ol>
          ) : (
            <pre data-testid="definition-json" className="overflow-x-auto text-xs text-gray-600">
              {JSON.stringify(redactMetadata(definition), null, 2)}
            </pre>
          )}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Configuration" description="Redacted view of stored workflow config." />
        <CardBody>
          <pre data-testid="config-json" className="overflow-x-auto text-xs text-gray-600">
            {JSON.stringify(redactMetadata(config), null, 2)}
          </pre>
          {Object.keys(config).length > 0 ? (
            <p className="mt-2 text-xs text-gray-600">Unlisted values are shown as {REDACTED}.</p>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

interface WorkflowDetailActionsProps {
  role: UserRole;
  status: WorkflowStatus;
  busy: boolean;
  onEdit: () => void;
  onActivate: () => void;
  onPause: () => void;
  onArchive: () => void;
  onDelete: () => void;
  onRunNow: () => void;
}

/** Exported for static-markup tests: permission + state dependent actions. */
export function WorkflowDetailActions({
  role,
  status,
  busy,
  onEdit,
  onActivate,
  onPause,
  onArchive,
  onDelete,
  onRunNow,
}: WorkflowDetailActionsProps) {
  const mayEdit = canEditWorkflow(role);
  const mayManage = canManageWorkflowLifecycle(role);
  const mayRun = canQueueExecution(role);
  if (!mayEdit && !mayManage && !mayRun) return null;

  const runReason = actionDisabledReason(
    status === "active",
    "Run now is available only for active workflows."
  );
  const deleteReason = actionDisabledReason(
    status === "draft" || status === "archived",
    "Only draft or archived workflows can be deleted."
  );

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {mayRun ? (
        <Button
          disabled={busy || runReason !== null}
          title={runReason ?? undefined}
          onClick={onRunNow}
        >
          Run now
        </Button>
      ) : null}
      {mayEdit ? (
        <Button variant="outline" disabled={busy} onClick={onEdit}>
          Edit
        </Button>
      ) : null}
      {mayManage ? (
        <>
          <Button
            variant="outline"
            disabled={busy || (status !== "draft" && status !== "paused")}
            title={
              status === "draft" || status === "paused"
                ? undefined
                : "Only draft or paused workflows can be activated."
            }
            onClick={onActivate}
          >
            Activate
          </Button>
          <Button
            variant="outline"
            disabled={busy || status !== "active"}
            title={status === "active" ? undefined : "Only active workflows can be paused."}
            onClick={onPause}
          >
            Pause
          </Button>
          <Button
            variant="outline"
            disabled={busy || status === "archived"}
            title={status === "archived" ? undefined : "Already archived."}
            onClick={onArchive}
          >
            Archive
          </Button>
          <Button
            variant="danger"
            disabled={busy || deleteReason !== null}
            title={deleteReason ?? undefined}
            onClick={onDelete}
          >
            Delete
          </Button>
        </>
      ) : null}
      {busy ? <DisabledActionReason reason="An action is in progress." /> : null}
    </div>
  );
}

export default function WorkflowDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const session = useAuth();
  const { id: workflowId } = use(params);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [triggers, setTriggers] = useState<WorkflowTrigger[]>([]);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runResult, setRunResult] = useState<WorkflowExecutionQueue | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editMode, setEditMode] = useState<"n8n" | "builtin">("n8n");
  const [formError, setFormError] = useState<string | null>(null);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [editingTrigger, setEditingTrigger] = useState<WorkflowTrigger | null>(null);
  const [triggerName, setTriggerName] = useState("");
  const [triggerType, setTriggerType] = useState<WorkflowTriggerType>("event");
  const [triggerEventType, setTriggerEventType] = useState("");
  const [triggerCron, setTriggerCron] = useState("");
  const [triggerError, setTriggerError] = useState<string | null>(null);

  // Effects use `fetchAll` (no synchronous setState); actions use `reload` so
  // a refetch visibly enters the loading state.
  const fetchAll = useCallback(() => {
    return Promise.all([
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
        setWorkflow(null);
        setTriggers([]);
        setExecutions([]);
        setError(err instanceof ApiRequestError ? err.message : "Failed to load workflow");
      })
      .finally(() => setLoading(false));
  }, [workflowId]);

  const reload = useCallback(() => {
    setLoading(true);
    return fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  if (!session) return null;
  const role = session.user.role;
  const canRead = canReadWorkflows(role);
  const canWrite = canWriteTriggers(role);
  const canEdit = canEditWorkflow(role);
  const canManage = canManageWorkflowLifecycle(role);
  const canQueue = canQueueExecution(role);

  const transition = (fn: () => Promise<unknown>) => {
    setBusy(true);
    fn()
      .then(() => {
        setError(null);
        return reload();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Action failed");
      })
      .finally(() => setBusy(false));
  };

  const runNow = () => {
    setBusy(true);
    setRunResult(null);
    queueWorkflowExecution({ workflow_id: workflowId })
      .then((result) => {
        setRunResult(result);
        setError(null);
        return reload();
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to queue execution");
      })
      .finally(() => setBusy(false));
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

  const openEdit = () => {
    if (!workflow) return;
    setEditName(workflow.name);
    setEditDescription(workflow.description ?? "");
    setEditMode(workflow.execution_mode);
    setFormError(null);
    setEditOpen(true);
  };

  const saveEdit = () => {
    if (!editName.trim()) {
      setFormError("Name is required");
      return;
    }
    setBusy(true);
    setFormError(null);
    updateWorkflow(workflowId, {
      name: editName.trim(),
      description: editDescription.trim() || null,
      execution_mode: editMode,
    })
      .then(() => {
        setEditOpen(false);
        return reload();
      })
      .catch((err: unknown) => {
        setFormError(err instanceof ApiRequestError ? err.message : "Failed to update workflow");
      })
      .finally(() => setBusy(false));
  };

  const openTriggerForm = (trigger: WorkflowTrigger | null) => {
    setEditingTrigger(trigger);
    setTriggerName(trigger?.name ?? "");
    setTriggerType(trigger?.trigger_type ?? "event");
    setTriggerEventType(trigger?.event_type ?? "");
    setTriggerCron(trigger?.schedule_cron ?? "");
    setTriggerError(null);
    setTriggerOpen(true);
  };

  const saveTrigger = () => {
    if (!triggerName.trim() || (triggerType === "event" && !triggerEventType.trim())) {
      setTriggerError("Name and event type are required");
      return;
    }
    setBusy(true);
    setTriggerError(null);
    const payload = {
      name: triggerName.trim(),
      trigger_type: triggerType,
      event_type: triggerType === "event" ? triggerEventType.trim() : undefined,
      schedule_cron: triggerType === "schedule" ? triggerCron.trim() : undefined,
    };
    const request = editingTrigger
      ? updateWorkflowTrigger(editingTrigger.id, payload)
      : createWorkflowTrigger({ ...payload, workflow_id: workflowId });
    request
      .then(() => {
        setTriggerOpen(false);
        return reload();
      })
      .catch((err: unknown) => {
        setTriggerError(err instanceof ApiRequestError ? err.message : "Failed to save trigger");
      })
      .finally(() => setBusy(false));
  };

  const toggleTrigger = (trigger: WorkflowTrigger) => {
    transition(() =>
      trigger.enabled ? disableWorkflowTrigger(trigger.id) : enableWorkflowTrigger(trigger.id)
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={canRead && workflow ? workflow.name : "Workflow"}
        description={
          canRead && workflow
            ? (workflow.description ?? "No description")
            : "Workflow definition and execution history."
        }
        actions={
          canRead && workflow ? (
            <>
              <a href={ROUTES.workflows} className="text-sm text-gray-500 hover:underline">
                ← Back
              </a>
              <WorkflowDetailActions
                role={role}
                status={workflow.status}
                busy={busy}
                onEdit={openEdit}
                onActivate={() => transition(() => activateWorkflow(workflowId))}
                onPause={() => transition(() => pauseWorkflow(workflowId))}
                onArchive={() => transition(() => archiveWorkflow(workflowId))}
                onDelete={() => setDeleteOpen(true)}
                onRunNow={runNow}
              />
            </>
          ) : undefined
        }
      />

      <AutomationListState
        denied={!canRead}
        deniedMessage="You do not have permission to view workflow definitions."
        loading={loading}
        loadingLabel="Loading workflow…"
        error={error}
        onRetry={() => void reload()}
        empty={!loading && !error && workflow === null}
        emptyTitle="Workflow not found"
        emptyDescription="The requested workflow is unavailable or no longer exists."
      />

      {canRead && !loading && !error && workflow ? (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
            <Badge tone={workflowStatusTone(workflow.status)}>
              {WORKFLOW_STATUS_LABELS[workflow.status]}
            </Badge>
            <span>Mode: {workflow.execution_mode}</span>
            <span>Version: v{workflow.version}</span>
            <span>Updated: {formatUtcOrNever(workflow.updated_at)}</span>
          </div>

          {runResult ? (
            <div
              role="status"
              data-state="run-result"
              className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-900"
            >
              Queued execution <span className="font-mono">{runResult.execution_id}</span> with
              status <span className="font-mono">{runResult.status}</span>.
            </div>
          ) : null}

          <WorkflowDefinitionView definition={workflow.definition} config={workflow.config} />

          <Card>
            <CardHeader
              title="Triggers"
              actions={
                canWrite ? (
                  <Button variant="outline" onClick={() => openTriggerForm(null)}>
                    Add trigger
                  </Button>
                ) : undefined
              }
            />
            <CardBody>
              {triggers.length === 0 ? (
                <EmptyState
                  title="No triggers"
                  description="Manage triggers from the Triggers page or add one here."
                />
              ) : (
                <Table>
                  <THead>
                    <tr>
                      <TH>Name</TH>
                      <TH>Type</TH>
                      <TH>Condition</TH>
                      <TH>Last fired (UTC)</TH>
                      <TH>Status</TH>
                      <TH>Actions</TH>
                    </tr>
                  </THead>
                  <TBody>
                    {triggers.map((trigger) => (
                      <TRow key={trigger.id}>
                        <TD className="font-medium text-gray-900">{trigger.name}</TD>
                        <TD className="text-gray-600">
                          {TRIGGER_TYPE_LABELS[trigger.trigger_type]}
                        </TD>
                        <TD className="text-gray-600">
                          {trigger.trigger_type === "event"
                            ? (trigger.event_type ?? "—")
                            : trigger.trigger_type === "schedule"
                              ? (trigger.schedule_cron ?? "—")
                              : "—"}
                        </TD>
                        <TD className="text-xs text-gray-600">
                          {formatUtcOrNever(trigger.last_fired_at)}
                        </TD>
                        <TD>
                          <Badge tone={trigger.enabled ? "green" : "gray"}>
                            {trigger.enabled ? "Enabled" : "Disabled"}
                          </Badge>
                        </TD>
                        <TD>
                          {canWrite ? (
                            <div className="flex gap-2">
                              <Button variant="ghost" onClick={() => openTriggerForm(trigger)}>
                                Edit
                              </Button>
                              <Button variant="outline" onClick={() => toggleTrigger(trigger)}>
                                {trigger.enabled ? "Disable" : "Enable"}
                              </Button>
                            </div>
                          ) : null}
                        </TD>
                      </TRow>
                    ))}
                  </TBody>
                </Table>
              )}
              <p className="mt-3 text-xs text-gray-500">
                <a href={ROUTES.triggers} className="hover:underline">
                  View all triggers →
                </a>
              </p>
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
                      <TH>Started (UTC)</TH>
                      <TH>Finished (UTC)</TH>
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
                        <TD className="text-xs text-gray-600">
                          {formatUtcOrNever(execution.started_at)}
                        </TD>
                        <TD className="text-xs text-gray-600">
                          {formatUtcOrNever(execution.finished_at)}
                        </TD>
                      </TRow>
                    ))}
                  </TBody>
                </Table>
              )}
              <p className="mt-3 text-xs text-gray-500">
                <a href={ROUTES.executions} className="hover:underline">
                  View all executions →
                </a>
              </p>
            </CardBody>
          </Card>
        </>
      ) : null}

      <Modal
        open={editOpen}
        title="Edit workflow"
        onClose={() => setEditOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={saveEdit} disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Name" htmlFor="wf-edit-name" required>
            <Input
              id="wf-edit-name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
          </Field>
          <Field label="Description" htmlFor="wf-edit-desc">
            <Input
              id="wf-edit-desc"
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
            />
          </Field>
          <Field label="Execution mode" htmlFor="wf-edit-mode">
            <Select
              id="wf-edit-mode"
              value={editMode}
              onChange={(e) => setEditMode(e.target.value as "n8n" | "builtin")}
            >
              <option value="n8n">n8n</option>
              <option value="builtin">Builtin</option>
            </Select>
          </Field>
          {formError ? (
            <p role="alert" className="text-sm text-red-600">
              {formError}
            </p>
          ) : null}
        </div>
      </Modal>

      <Modal
        open={triggerOpen}
        title={editingTrigger ? "Edit trigger" : "Add trigger"}
        onClose={() => setTriggerOpen(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setTriggerOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={saveTrigger} disabled={busy}>
              {busy ? "Saving…" : "Save"}
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
              />
            </Field>
          ) : null}
          {triggerType === "schedule" ? (
            <Field
              label="Cron expression"
              htmlFor="trig-cron"
              hint="UTC only; local-time scheduling is not available."
            >
              <Input
                id="trig-cron"
                value={triggerCron}
                onChange={(e) => setTriggerCron(e.target.value)}
                placeholder="e.g. 0 9 * * 1"
              />
            </Field>
          ) : null}
          {triggerError ? (
            <p role="alert" className="text-sm text-red-600">
              {triggerError}
            </p>
          ) : null}
        </div>
      </Modal>

      {deleteOpen ? (
        <Modal
          open
          title="Delete workflow"
          onClose={() => setDeleteOpen(false)}
          width="sm"
          footer={
            <>
              <Button variant="ghost" onClick={() => setDeleteOpen(false)} disabled={busy}>
                Cancel
              </Button>
              <Button variant="danger" onClick={handleDelete} disabled={busy}>
                Delete
              </Button>
            </>
          }
        >
          <p className="text-sm text-gray-600">This only works for draft or archived workflows.</p>
        </Modal>
      ) : null}
    </div>
  );
}
