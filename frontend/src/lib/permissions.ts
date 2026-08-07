// Client-side RBAC mirror of backend/app/core/permissions.py.
// Used to gate UI affordances (buttons, links, tabs). The backend remains the
// source of truth for enforcement — these checks only improve UX.
import type { UserRole } from "@/types";

export type PermissionKey =
  | "lead_read"
  | "lead_write"
  | "lead_delete"
  | "lead_assign"
  | "pipeline_manage"
  | "ai_manage"
  | "task_read"
  | "task_write"
  | "task_manage"
  | "note_read"
  | "note_write"
  | "search"
  | "export"
  | "analytics_read"
  | "team_manage"
  | "invite_manage"
  | "audit_read"
  | "automation_read"
  | "automation_write"
  | "automation_manage"
  | "automation_control"
  | "execution_read"
  | "execution_write"
  | "execution_manage"
  | "credential_read"
  | "credential_write"
  | "credential_delete";

const _READ: UserRole[] = ["owner", "admin", "manager", "member", "sales_agent", "viewer"];
const _WRITE: UserRole[] = ["owner", "admin", "manager", "member", "sales_agent"];
const _MANAGE: UserRole[] = ["owner", "admin", "manager"];
const _ADMIN_ONLY: UserRole[] = ["owner", "admin"];

const PERMISSION_MATRIX: Record<PermissionKey, UserRole[]> = {
  lead_read: _READ,
  lead_write: _WRITE,
  lead_delete: _MANAGE,
  lead_assign: _MANAGE,
  pipeline_manage: _ADMIN_ONLY,
  ai_manage: _MANAGE,
  task_read: _READ,
  task_write: _WRITE,
  task_manage: _MANAGE,
  note_read: _READ,
  note_write: _WRITE,
  search: _READ,
  export: _MANAGE,
  analytics_read: _MANAGE,
  team_manage: _ADMIN_ONLY,
  invite_manage: _ADMIN_ONLY,
  audit_read: _ADMIN_ONLY,
  automation_read: _READ,
  automation_write: _WRITE,
  automation_manage: _ADMIN_ONLY,
  automation_control: _ADMIN_ONLY,
  execution_read: _READ,
  execution_write: _WRITE,
  execution_manage: _ADMIN_ONLY,
  credential_read: _READ,
  credential_write: _WRITE,
  credential_delete: _ADMIN_ONLY,
};

/** Return whether a role may perform a named capability. */
export function can(role: UserRole, permission: PermissionKey): boolean {
  return PERMISSION_MATRIX[permission].includes(role);
}
