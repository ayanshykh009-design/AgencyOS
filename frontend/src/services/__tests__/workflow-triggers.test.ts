import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  createWorkflowTrigger,
  disableWorkflowTrigger,
  enableWorkflowTrigger,
  listWorkflowTriggers,
  updateWorkflowTrigger,
} from "@/services/workflow-triggers";
import type { User, WorkflowTrigger } from "@/types";

const USER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  organization_id: "22222222-2222-2222-2222-222222222222",
  email: "owner@example.com",
  full_name: "Owner",
  role: "owner",
  is_active: true,
  last_login_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const TRIGGER: WorkflowTrigger = {
  id: "77777777-7777-7777-7777-777777777777",
  organization_id: USER.organization_id,
  workflow_id: "33333333-3333-3333-3333-333333333333",
  name: "On lead created",
  trigger_type: "event",
  event_type: "lead_created",
  schedule_cron: null,
  config: {},
  enabled: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("workflow-triggers service", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clearSession();
    setSession({ accessToken: "access-123", refreshToken: "r", expiresIn: 3600, user: USER });
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("listWorkflowTriggers encodes workflow + enabled filters", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [TRIGGER], total: 1 }));

    const page = await listWorkflowTriggers({ workflowId: TRIGGER.workflow_id, enabled: true });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`workflow_id=${TRIGGER.workflow_id}`);
    expect(url).toContain("enabled=true");
  });

  it("createWorkflowTrigger POSTs with per-type fields", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TRIGGER));

    await createWorkflowTrigger({
      workflow_id: TRIGGER.workflow_id,
      name: "On lead created",
      trigger_type: "event",
      event_type: "lead_created",
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/workflow-triggers");
    expect(init.method).toBe("POST");
    const body = (init.body as string) ?? "";
    expect(body).toContain('"trigger_type":"event"');
    expect(body).toContain('"event_type":"lead_created"');
  });

  it("updateWorkflowTrigger PATCHes fields", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TRIGGER));

    await updateWorkflowTrigger(TRIGGER.id, { enabled: false });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/workflow-triggers/${TRIGGER.id}`);
    expect(init.method).toBe("PATCH");
  });

  it("enable/disable POST to their endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(TRIGGER))
      .mockResolvedValueOnce(jsonResponse(TRIGGER));

    await enableWorkflowTrigger(TRIGGER.id);
    let [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/workflow-triggers/${TRIGGER.id}/enable`);
    expect(init.method).toBe("POST");

    await disableWorkflowTrigger(TRIGGER.id);
    [url] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toContain("/disable");
  });
});
