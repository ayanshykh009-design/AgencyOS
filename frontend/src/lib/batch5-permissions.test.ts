import { describe, expect, it } from "vitest";

import {
  canCancelAIRun,
  canDispatchDraft,
  canManageFounder,
  canRunAI,
  canViewAI,
  canViewFounder,
} from "@/lib/batch5-permissions";
import type { UserRole } from "@/types";

const ROLES: UserRole[] = ["owner", "admin", "manager", "member", "sales_agent", "viewer"];

describe("Batch 5 UI permissions", () => {
  it("gates /ai page visibility and run on ai_run", () => {
    expect(ROLES.filter(canViewAI)).toEqual(["owner", "admin", "manager", "member", "sales_agent"]);
    expect(ROLES.filter(canRunAI)).toEqual(ROLES.filter(canViewAI));
  });

  it("allows Cancel for admins and owners only", () => {
    expect(ROLES.filter(canCancelAIRun)).toEqual(["owner", "admin"]);
    expect(canCancelAIRun("manager")).toBe(false);
    expect(canCancelAIRun("member")).toBe(false);
    expect(canCancelAIRun("sales_agent")).toBe(false);
    expect(canCancelAIRun("viewer")).toBe(false);
  });

  it("gates draft dispatch on lead_write", () => {
    expect(ROLES.filter(canDispatchDraft)).toEqual([
      "owner",
      "admin",
      "manager",
      "member",
      "sales_agent",
    ]);
    expect(canDispatchDraft("viewer")).toBe(false);
  });

  it("gates founder writes/decisions on founder_manage", () => {
    expect(ROLES.filter(canManageFounder)).toEqual(["owner", "admin", "manager"]);
    expect(canManageFounder("member")).toBe(false);
    expect(canManageFounder("sales_agent")).toBe(false);
    expect(canManageFounder("viewer")).toBe(false);
  });

  it("gates founder reads on founder_read for all roles", () => {
    expect(ROLES.filter(canViewFounder)).toEqual(ROLES);
  });
});
