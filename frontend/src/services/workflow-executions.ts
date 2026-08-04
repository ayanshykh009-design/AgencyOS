// Workflow executions service: queue, inspect, and manual lifecycle controls.
import { apiFetch } from "@/lib/api-client";
import type {
  ExecutionStatus,
  Page,
  WorkflowExecution,
  WorkflowExecutionCreateInput,
  WorkflowExecutionQueue,
} from "@/types";

export interface WorkflowExecutionQuery {
  status?: ExecutionStatus;
  workflowId?: string;
  limit?: number;
  offset?: number;
}

export async function listWorkflowExecutions(
  query: WorkflowExecutionQuery = {}
): Promise<Page<WorkflowExecution>> {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.workflowId) params.set("workflow_id", query.workflowId);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<WorkflowExecution>>(`/workflow-executions${qs ? `?${qs}` : ""}`);
}

export async function getWorkflowExecution(executionId: string): Promise<WorkflowExecution> {
  return apiFetch<WorkflowExecution>(`/workflow-executions/${executionId}`);
}

export async function queueWorkflowExecution(
  input: WorkflowExecutionCreateInput
): Promise<WorkflowExecutionQueue> {
  return apiFetch<WorkflowExecutionQueue>("/workflow-executions", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function startWorkflowExecution(executionId: string): Promise<WorkflowExecution> {
  return apiFetch<WorkflowExecution>(`/workflow-executions/${executionId}/start`, {
    method: "POST",
  });
}

export async function retryWorkflowExecution(executionId: string): Promise<WorkflowExecution> {
  return apiFetch<WorkflowExecution>(`/workflow-executions/${executionId}/retry`, {
    method: "POST",
  });
}

export async function cancelWorkflowExecution(executionId: string): Promise<WorkflowExecution> {
  return apiFetch<WorkflowExecution>(`/workflow-executions/${executionId}/cancel`, {
    method: "POST",
  });
}
