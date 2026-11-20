// Assignment service: rule management, manual assignment, bulk sweep, history.
import { apiFetch } from "@/lib/api-client";
import type {
  AssignmentLogEntry,
  AssignmentRule,
  AssignmentRuleWriteInput,
  Lead,
  Page,
} from "@/types";

export async function getAssignmentRule(): Promise<AssignmentRule | null> {
  return apiFetch<AssignmentRule | null>("/assignment/rules");
}

export async function upsertAssignmentRule(
  input: AssignmentRuleWriteInput
): Promise<AssignmentRule> {
  return apiFetch<AssignmentRule>("/assignment/rules", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function assignUnassignedLeads(): Promise<{ assigned: number }> {
  return apiFetch<{ assigned: number }>("/assignment/assign-unassigned", {
    method: "POST",
  });
}

export async function assignLead(
  leadId: string,
  input: { user_id?: string; reason?: string }
): Promise<Lead> {
  return apiFetch<Lead>(`/assignment/leads/${leadId}/assign`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export interface AssignmentHistoryQuery {
  /** Backend accepts 1–500 (default 50). */
  limit?: number;
  offset?: number;
}

/** Assignment history for a lead (backend order + pagination). */
export async function listAssignmentHistory(
  leadId: string,
  query: AssignmentHistoryQuery = {}
): Promise<Page<AssignmentLogEntry>> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const qs = params.toString();
  return apiFetch<Page<AssignmentLogEntry>>(
    `/assignment/leads/${leadId}/history${qs ? `?${qs}` : ""}`
  );
}
