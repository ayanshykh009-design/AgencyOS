// Workflow triggers service: CRUD and enable/disable.
import { apiFetch } from "@/lib/api-client";
import type {
  Page,
  WorkflowTrigger,
  WorkflowTriggerCreateInput,
  WorkflowTriggerUpdateInput,
} from "@/types";

export interface WorkflowTriggerQuery {
  workflowId?: string;
  enabled?: boolean;
  limit?: number;
  offset?: number;
}

export async function listWorkflowTriggers(
  query: WorkflowTriggerQuery = {}
): Promise<Page<WorkflowTrigger>> {
  const params = new URLSearchParams();
  if (query.workflowId) params.set("workflow_id", query.workflowId);
  if (query.enabled !== undefined) params.set("enabled", String(query.enabled));
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<WorkflowTrigger>>(`/workflow-triggers${qs ? `?${qs}` : ""}`);
}

export async function getWorkflowTrigger(triggerId: string): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(`/workflow-triggers/${triggerId}`);
}

export async function createWorkflowTrigger(
  input: WorkflowTriggerCreateInput
): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>("/workflow-triggers", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateWorkflowTrigger(
  triggerId: string,
  patch: WorkflowTriggerUpdateInput
): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(`/workflow-triggers/${triggerId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function enableWorkflowTrigger(triggerId: string): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(`/workflow-triggers/${triggerId}/enable`, { method: "POST" });
}

export async function disableWorkflowTrigger(triggerId: string): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(`/workflow-triggers/${triggerId}/disable`, { method: "POST" });
}

export async function deleteWorkflowTrigger(triggerId: string): Promise<void> {
  await apiFetch<void>(`/workflow-triggers/${triggerId}`, { method: "DELETE" });
}
