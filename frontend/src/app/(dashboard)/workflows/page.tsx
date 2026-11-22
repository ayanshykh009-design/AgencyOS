// Workflows: read-only list with real service-backed create, edit and
// lifecycle transitions. There is no workflow builder and no status PATCH.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  AutomationListState,
  DisabledActionReason,
  actionDisabledReason,
} from "@/components/automation/automation-states";
import {
  Badge,
  Button,
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
import { WORKFLOW_STATUS_LABELS, workflowStatusTone } from "@/lib/format";
import {
  canCreateWorkflow,
  canEditWorkflow,
  canManageWorkflowLifecycle,
  canReadWorkflows,
} from "@/lib/batch6-permissions";
import {
  activateWorkflow,
  archiveWorkflow,
  createWorkflow,
  deleteWorkflow,
  listWorkflows,
  pauseWorkflow,
  updateWorkflow,
} from "@/services/workflows";
import type { UserRole, Workflow, WorkflowStatus } from "@/types";

interface WorkflowRowActionsProps {
  role: UserRole;
  status: WorkflowStatus;
  busy: boolean;
  onEdit: () => void;
  onActivate: () => void;
  onPause: () => void;
  onArchive: () => void;
  onDelete: () => void;
}

/** Exported for static-markup tests: state- and permission-dependent actions. */
export function WorkflowRowActions({
  role,
  status,
  busy,
  onEdit,
  onActivate,
  onPause,
  onArchive,
  onDelete,
}: WorkflowRowActionsProps) {
  const mayEdit = canEditWorkflow(role);
  const mayManage = canManageWorkflowLifecycle(role);
  if (!mayEdit && !mayManage) return null;

  const activateReason = actionDisabledReason(
    status === "draft" || status === "paused",
    "Only draft or paused workflows can be activated."
  );
  const pauseReason = actionDisabledReason(
    status === "active",
    "Only active workflows can be paused."
  );
  const archiveReason = actionDisabledReason(
    status !== "archived",
    "This workflow is already archived."
  );
  const deleteReason = actionDisabledReason(
    status === "draft" || status === "archived",
    "Only draft or archived workflows can be deleted."
  );

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {mayEdit ? (
        <Button variant="ghost" disabled={busy} onClick={onEdit}>
          Edit
        </Button>
      ) : null}
      {mayManage ? (
        <>
          <Button
            variant="outline"
            disabled={busy || activateReason !== null}
            title={activateReason ?? undefined}
            onClick={onActivate}
          >
            Activate
          </Button>
          <Button
            variant="outline"
            disabled={busy || pauseReason !== null}
            title={pauseReason ?? undefined}
            onClick={onPause}
          >
            Pause
          </Button>
          <Button
            variant="outline"
            disabled={busy || archiveReason !== null}
            title={archiveReason ?? undefined}
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

export default function WorkflowsPage() {
  const session = useAuth();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [formTarget, setFormTarget] = useState<Workflow | "new" | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [executionMode, setExecutionMode] = useState<"n8n" | "builtin">("n8n");
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Workflow | null>(null);

  // The fetch itself never calls setState synchronously; effects call it
  // directly. Event handlers use `reload` so a refetch shows the loading state.
  const fetchWorkflows = useCallback((filter: string) => {
    return listWorkflows({
      status: (filter || undefined) as WorkflowStatus | undefined,
      limit: 200,
    })
      .then((page) => {
        setWorkflows(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setWorkflows([]);
        setError(err instanceof ApiRequestError ? err.message : "Failed to load workflows");
      })
      .finally(() => setLoading(false));
  }, []);

  const reload = useCallback(
    (filter: string) => {
      setLoading(true);
      return fetchWorkflows(filter);
    },
    [fetchWorkflows]
  );

  useEffect(() => {
    void fetchWorkflows(statusFilter);
  }, [fetchWorkflows, statusFilter]);

  if (!session) return null;
  const role = session.user.role;
  const canRead = canReadWorkflows(role);
  const canCreate = canCreateWorkflow(role);

  const openForm = (target: Workflow | "new") => {
    setFormTarget(target);
    setFormError(null);
    if (target === "new") {
      setName("");
      setDescription("");
      setExecutionMode("n8n");
    } else {
      setName(target.name);
      setDescription(target.description ?? "");
      setExecutionMode(target.execution_mode);
    }
  };

  const saveForm = () => {
    if (!name.trim()) {
      setFormError("Name is required");
      return;
    }
    const target = formTarget;
    if (!target) return;
    setBusyId(target === "new" ? "new" : target.id);
    setFormError(null);
    const payload = {
      name: name.trim(),
      description: description.trim() || undefined,
      execution_mode: executionMode,
    };
    const request =
      target === "new"
        ? createWorkflow(payload)
        : updateWorkflow(target.id, {
            ...payload,
            description: description.trim() || null,
          });
    request
      .then(() => {
        setFormTarget(null);
        return reload(statusFilter);
      })
      .catch((err: unknown) => {
        setFormError(err instanceof ApiRequestError ? err.message : "Failed to save workflow");
      })
      .finally(() => setBusyId(null));
  };

  const transition = (workflow: Workflow, fn: (id: string) => Promise<unknown>) => {
    setBusyId(workflow.id);
    return fn(workflow.id)
      .then(() => reload(statusFilter))
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Action failed");
      })
      .finally(() => setBusyId(null));
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    transition(deleteTarget, deleteWorkflow).finally(() => setDeleteTarget(null));
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Workflows"
        description="Automation definitions executed by the workflow engine. Read-only visualization; no builder."
        actions={
          canRead && canCreate ? (
            <Button onClick={() => openForm("new")}>New workflow</Button>
          ) : undefined
        }
      />

      <AutomationListState
        denied={!canRead}
        deniedMessage="You do not have permission to view workflows."
        loading={loading}
        loadingLabel="Loading workflows…"
        error={error}
        onRetry={() => void reload(statusFilter)}
        empty={workflows.length === 0}
        emptyTitle="No workflows"
        emptyDescription="Create a workflow to start automating your operations."
      />

      {canRead && !loading && !error && workflows.length > 0 ? (
        <>
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-52"
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            {Object.entries(WORKFLOW_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>

          <Table>
            <THead>
              <tr>
                <TH>Name</TH>
                <TH>Status</TH>
                <TH>Mode</TH>
                <TH>Version</TH>
                <TH>Updated</TH>
                <TH>Actions</TH>
              </tr>
            </THead>
            <TBody>
              {workflows.map((workflow) => (
                <TRow key={workflow.id}>
                  <TD>
                    <a
                      href={ROUTES.workflowDetail(workflow.id)}
                      className="font-medium text-gray-900 hover:underline"
                    >
                      {workflow.name}
                    </a>
                    {workflow.description ? (
                      <p className="mt-0.5 max-w-md truncate text-xs text-gray-500">
                        {workflow.description}
                      </p>
                    ) : null}
                  </TD>
                  <TD>
                    <Badge tone={workflowStatusTone(workflow.status)}>{workflow.status}</Badge>
                  </TD>
                  <TD className="text-gray-600">{workflow.execution_mode}</TD>
                  <TD className="text-gray-600">v{workflow.version}</TD>
                  <TD className="text-xs text-gray-600">
                    {new Date(workflow.updated_at).toISOString()} (UTC)
                  </TD>
                  <TD>
                    <WorkflowRowActions
                      role={role}
                      status={workflow.status}
                      busy={busyId === workflow.id}
                      onEdit={() => openForm(workflow)}
                      onActivate={() => transition(workflow, activateWorkflow)}
                      onPause={() => transition(workflow, pauseWorkflow)}
                      onArchive={() => transition(workflow, archiveWorkflow)}
                      onDelete={() => setDeleteTarget(workflow)}
                    />
                  </TD>
                </TRow>
              ))}
            </TBody>
          </Table>
        </>
      ) : null}

      <Modal
        open={formTarget !== null}
        title={formTarget === "new" ? "New workflow" : "Edit workflow"}
        onClose={() => setFormTarget(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setFormTarget(null)} disabled={busyId !== null}>
              Cancel
            </Button>
            <Button onClick={saveForm} disabled={busyId !== null}>
              {busyId !== null ? "Saving…" : "Save"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Name" htmlFor="wf-name" required>
            <Input
              id="wf-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Lead intake → research"
            />
          </Field>
          <Field label="Description" htmlFor="wf-desc">
            <Input
              id="wf-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional summary"
            />
          </Field>
          <Field
            label="Execution mode"
            htmlFor="wf-mode"
            hint="Definition and config are edited on the server, not in this UI."
          >
            <Select
              id="wf-mode"
              value={executionMode}
              onChange={(e) => setExecutionMode(e.target.value as "n8n" | "builtin")}
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

      {deleteTarget ? (
        <Modal
          open
          title="Delete workflow"
          onClose={() => setDeleteTarget(null)}
          width="sm"
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => setDeleteTarget(null)}
                disabled={busyId !== null}
              >
                Cancel
              </Button>
              <Button variant="danger" onClick={confirmDelete} disabled={busyId !== null}>
                Delete
              </Button>
            </>
          }
        >
          <p className="text-sm text-gray-600">
            Delete &ldquo;{deleteTarget.name}&rdquo;? Only draft or archived workflows can be
            deleted.
          </p>
        </Modal>
      ) : null}
    </div>
  );
}
