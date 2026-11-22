// Batch 6 UI permission helpers for the six canonical Automation routes.
//
// Thin wrappers over the shared RBAC mirror. The keys below mirror the actual
// backend endpoint dependencies (verified from backend/app/api/v1/endpoints/):
//   workflows.py          WORKFLOW_READ / WORKFLOW_WRITE / WORKFLOW_MANAGE
//   workflow_executions.py EXECUTION_READ for reads, WORKFLOW_WRITE for writes
//   credentials.py        CREDENTIAL_MANAGE for every endpoint
//   deliveries.py         DELIVERY_READ for reads, DELIVERY_MANAGE for writes
//   workflow_triggers.py  AUTOMATION_READ for the org-wide list and
//                         AUTOMATION_WRITE for create/update/enable/disable.
//
// Frontend checks are UX only. The backend remains the authority; the shared
// matrix in `@/lib/permissions` is deliberately untouched.

import { can } from "@/lib/permissions";
import type { UserRole } from "@/types";

// --- Workflows ---------------------------------------------------------------

/** Workflow list and detail reads (`workflow_read`). */
export function canReadWorkflows(role: UserRole): boolean {
  return can(role, "workflow_read");
}

/** Workflow create (`workflow_write`). */
export function canCreateWorkflow(role: UserRole): boolean {
  return can(role, "workflow_write");
}

/** Workflow metadata edit (`workflow_write`, not `workflow_manage`). */
export function canEditWorkflow(role: UserRole): boolean {
  return can(role, "workflow_write");
}

/** Activate, pause, archive and delete (`workflow_manage`). */
export function canManageWorkflowLifecycle(role: UserRole): boolean {
  return can(role, "workflow_manage");
}

// --- Automation surface ------------------------------------------------------

/** Shared automation read gate used by the navigation and trigger list. */
export function canReadAutomation(role: UserRole): boolean {
  return can(role, "automation_read");
}

/** Shared automation write key (kept for completeness; not used to broaden UI). */
export function canWriteAutomation(role: UserRole): boolean {
  return can(role, "automation_write");
}

/** Admin-only shared matrix mapping — deliberately preserved. */
export function canManageAutomation(role: UserRole): boolean {
  return can(role, "automation_manage");
}

/** Admin-only automation control key (kill switch surface). */
export function canControlAutomation(role: UserRole): boolean {
  return can(role, "automation_control");
}

// --- Triggers ----------------------------------------------------------------

/** Org-wide trigger list (backend `/workflow-triggers` uses `automation_read`). */
export function canReadTriggers(role: UserRole): boolean {
  return can(role, "automation_read");
}

/**
 * Trigger create/edit/enable/disable on the top-level `/workflow-triggers`
 * endpoints, whose writes require `automation_write`.
 */
export function canWriteTriggers(role: UserRole): boolean {
  return can(role, "automation_write");
}

// --- Executions --------------------------------------------------------------

/** Execution list and detail reads (`execution_read`). */
export function canReadExecutions(role: UserRole): boolean {
  return can(role, "execution_read");
}

/** Queue a new execution (`workflow_write` — NOT `agent_manage`). */
export function canQueueExecution(role: UserRole): boolean {
  return can(role, "workflow_write");
}

/** Start a queued execution (`workflow_write`). */
export function canStartExecution(role: UserRole): boolean {
  return can(role, "workflow_write");
}

/** Retry a failed execution (`workflow_write`). */
export function canRetryExecution(role: UserRole): boolean {
  return can(role, "workflow_write");
}

/** Cancel a non-terminal execution (`workflow_write`). */
export function canCancelExecution(role: UserRole): boolean {
  return can(role, "workflow_write");
}

// --- Credentials -------------------------------------------------------------

/**
 * Every credentials endpoint (list, create, update, delete, rotate) requires
 * `credential_manage`. The page is therefore admin/owner-only.
 */
export function canManageCredentials(role: UserRole): boolean {
  return can(role, "credential_manage");
}

// --- Deliveries --------------------------------------------------------------

/** Delivery list and metrics (`delivery_read`). */
export function canReadDeliveries(role: UserRole): boolean {
  return can(role, "delivery_read");
}

/** Enqueue a delivery (`delivery_write`). Kept for mapping completeness; the
 * UI does not expose a live-provider dispatch form because no channel provider
 * is registered in Batch 6. */
export function canWriteDeliveries(role: UserRole): boolean {
  return can(role, "delivery_write");
}

/** Manual delivery retry (`delivery_manage`). */
export function canRetryDelivery(role: UserRole): boolean {
  return can(role, "delivery_manage");
}

/** Delivery cancel (`delivery_manage`). */
export function canCancelDelivery(role: UserRole): boolean {
  return can(role, "delivery_manage");
}

/** Manual delivery dispatch (`delivery_manage`). No live provider call is made. */
export function canDispatchDelivery(role: UserRole): boolean {
  return can(role, "delivery_manage");
}
