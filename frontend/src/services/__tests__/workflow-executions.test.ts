import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  cancelWorkflowExecution,
  getWorkflowExecution,
  listWorkflowExecutions,
  queueWorkflowExecution,
  retryWorkflowExecution,
  startWorkflowExecution,
} from "@/services/workflow-executions";
import type { User, WorkflowExecution } from "@/types";

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

const EXECUTION: WorkflowExecution = {
  id: "66666666-6666-6666-6666-666666666666",
  organization_id: USER.organization_id,
  workflow_id: "33333333-3333-3333-3333-333333333333",
  trigger_id: null,
  status: "queued",
  attempts: 0,
  max_attempts: 3,
  retry_delay_seconds: 60,
  retry_backoff: "exponential",
  next_retry_at: null,
  input: {},
  output: null,
  error: null,
  requested_by_user_id: USER.id,
  trace_id: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  started_at: null,
  finished_at: null,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("workflow-executions service", () => {
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

  it("listWorkflowExecutions encodes filters", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [EXECUTION], total: 1 }));

    const page = await listWorkflowExecutions({
      status: "running",
      workflowId: EXECUTION.workflow_id,
    });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("status=running");
    expect(url).toContain(`workflow_id=${EXECUTION.workflow_id}`);
  });

  it("getWorkflowExecution fetches one execution", async () => {
    fetchMock.mockResolvedValue(jsonResponse(EXECUTION));

    const execution = await getWorkflowExecution(EXECUTION.id);

    expect(execution.status).toBe("queued");
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/workflow-executions/${EXECUTION.id}`);
  });

  it("queueWorkflowExecution POSTs with retry policy", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ execution_id: EXECUTION.id, status: "queued" }));

    const result = await queueWorkflowExecution({
      workflow_id: EXECUTION.workflow_id,
      max_attempts: 5,
      retry_delay_seconds: 120,
    });

    expect(result.execution_id).toBe(EXECUTION.id);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/workflow-executions");
    expect(init.method).toBe("POST");
    const body = (init.body as string) ?? "";
    expect(body).toContain('"max_attempts":5');
    expect(body).toContain('"retry_delay_seconds":120');
  });

  it("start/retry/cancel POST to lifecycle endpoints", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(EXECUTION))
      .mockResolvedValueOnce(jsonResponse(EXECUTION))
      .mockResolvedValueOnce(jsonResponse(EXECUTION));

    await startWorkflowExecution(EXECUTION.id);
    let [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/workflow-executions/${EXECUTION.id}/start`);
    expect(init.method).toBe("POST");

    await retryWorkflowExecution(EXECUTION.id);
    [url] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toContain("/retry");

    await cancelWorkflowExecution(EXECUTION.id);
    [url] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(url).toContain("/cancel");
  });
});
