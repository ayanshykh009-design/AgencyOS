// Workflow events service: publish and inspect inbound domain events.
import { apiFetch } from "@/lib/api-client";
import type { Page, WorkflowEvent, WorkflowEventPublish, WorkflowEventPublishInput } from "@/types";

export interface WorkflowEventQuery {
  eventType?: string;
  consumed?: boolean;
  limit?: number;
  offset?: number;
}

export async function listWorkflowEvents(
  query: WorkflowEventQuery = {}
): Promise<Page<WorkflowEvent>> {
  const params = new URLSearchParams();
  if (query.eventType) params.set("event_type", query.eventType);
  if (query.consumed !== undefined) params.set("consumed", String(query.consumed));
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<WorkflowEvent>>(`/workflow-events${qs ? `?${qs}` : ""}`);
}

export async function publishWorkflowEvent(
  input: WorkflowEventPublishInput
): Promise<WorkflowEventPublish> {
  return apiFetch<WorkflowEventPublish>("/workflow-events", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
