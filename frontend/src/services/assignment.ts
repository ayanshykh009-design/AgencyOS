// Assignment service: rule management, manual assignment, bulk sweep.
import { apiFetch } from "@/lib/api-client";
import type { AssignmentRule, AssignmentRuleWriteInput, Lead } from "@/types";

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
