import { describe, expect, it } from "vitest";

import {
  canCancelDelivery,
  canCancelExecution,
  canControlAutomation,
  canCreateWorkflow,
  canDispatchDelivery,
  canEditWorkflow,
  canManageAutomation,
  canManageCredentials,
  canManageWorkflowLifecycle,
  canQueueExecution,
  canReadAutomation,
  canReadDeliveries,
  canReadExecutions,
  canReadTriggers,
  canReadWorkflows,
  canRetryDelivery,
  canRetryExecution,
  canStartExecution,
  canWriteAutomation,
  canWriteDeliveries,
  canWriteTriggers,
} from "@/lib/batch6-permissions";
import type { UserRole } from "@/types";

const ROLES: UserRole[] = ["owner", "admin", "manager", "member", "sales_agent", "viewer"];
const READ = ["owner", "admin", "manager", "member", "sales_agent", "viewer"];
const WRITE = ["owner", "admin", "manager", "member", "sales_agent"];
const MANAGE = ["owner", "admin", "manager"];
const ADMIN = ["owner", "admin"];

function rolesWhere(fn: (role: UserRole) => boolean): UserRole[] {
  return ROLES.filter(fn);
}

describe("Batch 6 UI permissions", () => {
  it("gates workflow reads on workflow_read", () => {
    expect(rolesWhere(canReadWorkflows)).toEqual(READ);
  });

  it("gates workflow create/edit on workflow_write", () => {
    expect(rolesWhere(canCreateWorkflow)).toEqual(WRITE);
    expect(rolesWhere(canEditWorkflow)).toEqual(WRITE);
    expect(canCreateWorkflow("viewer")).toBe(false);
  });

  it("gates workflow lifecycle on workflow_manage", () => {
    expect(rolesWhere(canManageWorkflowLifecycle)).toEqual(MANAGE);
    expect(canManageWorkflowLifecycle("member")).toBe(false);
    expect(canManageWorkflowLifecycle("sales_agent")).toBe(false);
    expect(canManageWorkflowLifecycle("viewer")).toBe(false);
  });

  it("keeps automation_manage and automation_control admin-only", () => {
    expect(rolesWhere(canManageAutomation)).toEqual(ADMIN);
    expect(rolesWhere(canControlAutomation)).toEqual(ADMIN);
    expect(rolesWhere(canReadAutomation)).toEqual(READ);
    expect(rolesWhere(canWriteAutomation)).toEqual(WRITE);
  });

  it("gates trigger mutation on workflow_write and trigger reads on automation_read", () => {
    expect(rolesWhere(canWriteTriggers)).toEqual(WRITE);
    expect(rolesWhere(canReadTriggers)).toEqual(READ);
    expect(canWriteTriggers("viewer")).toBe(false);
  });

  it("gates every execution read on execution_read and every write on workflow_write", () => {
    expect(rolesWhere(canReadExecutions)).toEqual(READ);
    expect(rolesWhere(canQueueExecution)).toEqual(WRITE);
    expect(rolesWhere(canStartExecution)).toEqual(WRITE);
    expect(rolesWhere(canRetryExecution)).toEqual(WRITE);
    expect(rolesWhere(canCancelExecution)).toEqual(WRITE);
    // Explicitly never agent_manage (admin-only) for execution writes.
    expect(canRetryExecution("member")).toBe(true);
    expect(canCancelExecution("sales_agent")).toBe(true);
    expect(canQueueExecution("viewer")).toBe(false);
  });

  it("requires credential_manage for the entire credentials surface", () => {
    expect(rolesWhere(canManageCredentials)).toEqual(ADMIN);
    expect(canManageCredentials("manager")).toBe(false);
    expect(canManageCredentials("member")).toBe(false);
  });

  it("splits delivery reads from retry/cancel/dispatch writes", () => {
    expect(rolesWhere(canReadDeliveries)).toEqual(READ);
    expect(rolesWhere(canWriteDeliveries)).toEqual(WRITE);
    expect(rolesWhere(canRetryDelivery)).toEqual(ADMIN);
    expect(rolesWhere(canCancelDelivery)).toEqual(ADMIN);
    expect(rolesWhere(canDispatchDelivery)).toEqual(ADMIN);
    expect(canRetryDelivery("manager")).toBe(false);
  });
});
