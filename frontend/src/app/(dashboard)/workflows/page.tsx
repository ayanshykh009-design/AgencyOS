// Workflows: list and create automation workflows.
"use client";

import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Button,
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
import { WORKFLOW_STATUS_LABELS, workflowStatusTone } from "@/lib/format";
import { can } from "@/lib/permissions";
import { createWorkflow, listWorkflows } from "@/services/workflows";
import type { Workflow, WorkflowStatus } from "@/types";

export default function WorkflowsPage() {
  const session = useAuth();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [executionMode, setExecutionMode] = useState<"n8n" | "builtin">("n8n");
  const [createError, setCreateError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback((filter: string) => {
    listWorkflows({ status: (filter || undefined) as WorkflowStatus | undefined, limit: 200 })
      .then((page) => {
        setWorkflows(page.items);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : "Failed to load workflows");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(statusFilter);
  }, [load, statusFilter]);

  if (!session) return null;
  const canWrite = can(session.user.role, "automation_write");

  const handleCreate = () => {
    if (!name.trim()) {
      setCreateError("Name is required");
      return;
    }
    setBusy(true);
    setCreateError(null);
    createWorkflow({
      name: name.trim(),
      description: description.trim() || undefined,
      execution_mode: executionMode,
    })
      .then(() => {
        setCreating(false);
        setName("");
        setDescription("");
        setExecutionMode("n8n");
        load(statusFilter);
      })
      .catch((err: unknown) => {
        setCreateError(err instanceof ApiRequestError ? err.message : "Failed to create workflow");
      })
      .finally(() => setBusy(false));
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Workflows"
        description="Automation definitions executed by the workflow engine."
        actions={
          canWrite ? <Button onClick={() => setCreating(true)}>New workflow</Button> : undefined
        }
      />

      <Select
        value={statusFilter}
        onChange={(e) => setStatusFilter(e.target.value)}
        className="w-52"
      >
        <option value="">All statuses</option>
        {Object.entries(WORKFLOW_STATUS_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </Select>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {loading ? (
        <Spinner label="Loading workflows…" />
      ) : workflows.length === 0 ? (
        <EmptyState
          title="No workflows"
          description="Create a workflow to start automating your operations."
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Name</TH>
              <TH>Status</TH>
              <TH>Mode</TH>
              <TH>Version</TH>
              <TH>Updated</TH>
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
                <TD className="text-xs text-gray-400">
                  {new Date(workflow.updated_at).toLocaleDateString()}
                </TD>
              </TRow>
            ))}
          </TBody>
        </Table>
      )}

      <Modal
        open={creating}
        title="New workflow"
        onClose={() => setCreating(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={busy}>
              {busy ? "Creating…" : "Create"}
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
          <Field label="Execution mode" htmlFor="wf-mode">
            <Select
              id="wf-mode"
              value={executionMode}
              onChange={(e) => setExecutionMode(e.target.value as "n8n" | "builtin")}
            >
              <option value="n8n">n8n</option>
              <option value="builtin">Builtin</option>
            </Select>
          </Field>
          {createError ? <p className="text-sm text-red-600">{createError}</p> : null}
        </div>
      </Modal>
    </div>
  );
}
