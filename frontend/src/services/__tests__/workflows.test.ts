import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  activateWorkflow,
  archiveWorkflow,
  createWorkflow,
  deleteWorkflow,
  getWorkflow,
  listActiveWorkflows,
  listWorkflows,
  pauseWorkflow,
  updateWorkflow,
} from "@/services/workflows";
import type { User, Workflow } from "@/types";

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

const WORKFLOW: Workflow = {
  id: "33333333-3333-3333-3333-333333333333",
  organization_id: USER.organization_id,
  name: "Lead intake",
  description: null,
  definition: {},
  status: "draft",
  version: 1,
  execution_mode: "n8n",
  config: {},
  created_by_user_id: USER.id,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("workflows service", () => {
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

  it("listWorkflows encodes the status filter", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [WORKFLOW], total: 1 }));

    const page = await listWorkflows({ status: "active" });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/workflows?");
    expect(url).toContain("status=active");
  });

  it("listActiveWorkflows hits the active endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse([WORKFLOW]));

    const items = await listActiveWorkflows();

    expect(items).toHaveLength(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/workflows/active");
  });

  it("getWorkflow fetches a single workflow", async () => {
    fetchMock.mockResolvedValue(jsonResponse(WORKFLOW));

    const workflow = await getWorkflow(WORKFLOW.id);

    expect(workflow.name).toBe("Lead intake");
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/workflows/${WORKFLOW.id}`);
  });

  it("createWorkflow POSTs the payload", async () => {
    fetchMock.mockResolvedValue(jsonResponse(WORKFLOW));

    await createWorkflow({ name: "Lead intake", execution_mode: "n8n" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"name":"Lead intake"');
  });

  it("updateWorkflow PATCHes fields", async () => {
    fetchMock.mockResolvedValue(jsonResponse(WORKFLOW));

    await updateWorkflow(WORKFLOW.id, { description: "New" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/workflows/${WORKFLOW.id}`);
    expect(init.method).toBe("PATCH");
    expect((init.body as string) ?? "").toContain('"description":"New"');
  });

  it("status transitions POST to their endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ...WORKFLOW, status: "active" }))
      .mockResolvedValueOnce(jsonResponse({ ...WORKFLOW, status: "paused" }))
      .mockResolvedValueOnce(jsonResponse({ ...WORKFLOW, status: "archived" }));

    await activateWorkflow(WORKFLOW.id);
    let [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/workflows/${WORKFLOW.id}/activate`);
    expect(init.method).toBe("POST");

    await pauseWorkflow(WORKFLOW.id);
    [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toContain("/pause");
    expect(init.method).toBe("POST");

    await archiveWorkflow(WORKFLOW.id);
    [url, init] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(url).toContain("/archive");
    expect(init.method).toBe("POST");
  });

  it("deleteWorkflow issues a DELETE", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await deleteWorkflow(WORKFLOW.id);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("DELETE");
  });
});
