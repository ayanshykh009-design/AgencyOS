// Batch 5 UI permission helpers. Thin wrappers over the shared RBAC mirror so
// all five pages gate the same permission key. The backend remains the source
// of truth; these checks only control what is rendered/enabled.

import { can } from "@/lib/permissions";
import type { UserRole } from "@/types";

/** `/ai` page visibility: backend /ai/run requires AI_RUN. */
export function canViewAI(role: UserRole): boolean {
  return can(role, "ai_run");
}

/** Queue an AI run (same key as page visibility). */
export function canRunAI(role: UserRole): boolean {
  return can(role, "ai_run");
}

/** Cancel a run: backend cancel requires AGENT_MANAGE (admin/owner only). */
export function canCancelAIRun(role: UserRole): boolean {
  return can(role, "agent_manage");
}

/** Dispatch a draft to n8n requires lead write permission. */
export function canDispatchDraft(role: UserRole): boolean {
  return can(role, "lead_write");
}

/** Founder chat writes, conversation deletes, and proposal decisions. */
export function canManageFounder(role: UserRole): boolean {
  return can(role, "founder_manage");
}

/** Read access to founder chat, proposals, and intelligence. */
export function canViewFounder(role: UserRole): boolean {
  return can(role, "founder_read");
}
