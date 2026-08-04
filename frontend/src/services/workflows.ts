// Workflows service: CRUD and status transitions.
import { apiFetch } from "@/lib/api-client";
import type { Page, Workflow, WorkflowCreateInput, WorkflowUpdateInput } from "@/types";

export interface WorkflowQuery {
  status?: Workflow["status"];
  limit?: number;
  offset?: number;
}

export async function listWorkflows(query: WorkflowQuery = {}): Promise<Page<Workflow>> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<Workflow>>(`/workflows${qs ? `?${qs}` : ""}`);
}

export async function listActiveWorkflows(): Promise<Workflow[]> {
  return apiFetch<Workflow[]>("/workflows/active");
}

export async function getWorkflow(workflowId: string): Promise<Workflow> {
  return apiFetch<Workflow>(`/workflows/${workflowId}`);
}

export async function createWorkflow(input: WorkflowCreateInput): Promise<Workflow> {
  return apiFetch<Workflow>("/workflows", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateWorkflow(
  workflowId: string,
  patch: WorkflowUpdateInput
): Promise<Workflow> {
  return apiFetch<Workflow>(`/workflows/${workflowId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function activateWorkflow(workflowId: string): Promise<Workflow> {
  return apiFetch<Workflow>(`/workflows/${workflowId}/activate`, { method: "POST" });
}

export async function pauseWorkflow(workflowId: string): Promise<Workflow> {
  return apiFetch<Workflow>(`/workflows/${workflowId}/pause`, { method: "POST" });
}

export async function archiveWorkflow(workflowId: string): Promise<Workflow> {
  return apiFetch<Workflow>(`/workflows/${workflowId}/archive`, { method: "POST" });
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  await apiFetch<void>(`/workflows/${workflowId}`, { method: "DELETE" });
}
