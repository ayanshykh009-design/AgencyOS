import { describe, expect, it } from "vitest";

import { can } from "@/lib/permissions";
import type { UserRole } from "@/types";

const ROLES: UserRole[] = ["owner", "admin", "manager", "member", "sales_agent", "viewer"];

describe("permissions", () => {
  it("every role can read leads and tasks", () => {
    for (const role of ROLES) {
      expect(can(role, "lead_read")).toBe(true);
      expect(can(role, "task_read")).toBe(true);
      expect(can(role, "search")).toBe(true);
    }
  });

  it("viewers cannot write leads or notes", () => {
    expect(can("viewer", "lead_write")).toBe(false);
    expect(can("viewer", "note_write")).toBe(false);
    expect(can("viewer", "task_write")).toBe(false);
  });

  it("admin-only permissions require owner or admin", () => {
    for (const permission of [
      "audit_read",
      "team_manage",
      "invite_manage",
      "pipeline_manage",
    ] as const) {
      expect(can("owner", permission)).toBe(true);
      expect(can("admin", permission)).toBe(true);
      expect(can("manager", permission)).toBe(false);
      expect(can("member", permission)).toBe(false);
      expect(can("sales_agent", permission)).toBe(false);
      expect(can("viewer", permission)).toBe(false);
    }
  });

  it("manager-level permissions allow owner, admin, and manager", () => {
    for (const permission of [
      "export",
      "analytics_read",
      "lead_assign",
      "task_manage",
      "lead_delete",
      "ai_manage",
    ] as const) {
      expect(can("owner", permission)).toBe(true);
      expect(can("admin", permission)).toBe(true);
      expect(can("manager", permission)).toBe(true);
      expect(can("member", permission)).toBe(false);
      expect(can("viewer", permission)).toBe(false);
    }
  });

  it("every role can read Phase 5D context", () => {
    for (const role of ROLES) {
      expect(can(role, "memory_read")).toBe(true);
      expect(can(role, "approval_read")).toBe(true);
      expect(can(role, "notification_read")).toBe(true);
      expect(can(role, "agent_read")).toBe(true);
    }
  });

  it("notification_write is a team-level action", () => {
    for (const role of ["owner", "admin", "manager", "member", "sales_agent"] as const) {
      expect(can(role, "notification_write")).toBe(true);
    }
    expect(can("viewer", "notification_write")).toBe(false);
  });

  it("manager-level Phase 5D permissions require owner, admin, or manager", () => {
    for (const permission of ["memory_write", "approval_manage", "growth_read"] as const) {
      expect(can("owner", permission)).toBe(true);
      expect(can("admin", permission)).toBe(true);
      expect(can("manager", permission)).toBe(true);
      expect(can("member", permission)).toBe(false);
      expect(can("sales_agent", permission)).toBe(false);
      expect(can("viewer", permission)).toBe(false);
    }
  });

  it("admin-only Phase 5D permissions require owner or admin", () => {
    for (const permission of ["growth_manage", "agent_manage"] as const) {
      expect(can("owner", permission)).toBe(true);
      expect(can("admin", permission)).toBe(true);
      expect(can("manager", permission)).toBe(false);
      expect(can("member", permission)).toBe(false);
      expect(can("sales_agent", permission)).toBe(false);
      expect(can("viewer", permission)).toBe(false);
    }
  });
});
