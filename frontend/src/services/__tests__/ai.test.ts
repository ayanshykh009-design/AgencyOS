import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  cancelAgentRun,
  dispatchDraft,
  getAICapabilities,
  getAISettings,
  getAgentRun,
  listAITools,
  runBrain,
  updateAISettings,
} from "@/services/ai";
import type { User } from "@/types";

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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ai service", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clearSession();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("listAITools GETs the manifest", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse([{ name: "lead_research", description: "d", parameters: {} }])
    );

    const tools = await listAITools();

    expect(tools).toHaveLength(1);
    expect(tools[0].name).toBe("lead_research");
  });

  it("runBrain POSTs the goal and lead and returns the queued run", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "run-123",
        organization_id: USER.organization_id,
        agent_name: "ai_brain",
        status: "queued",
        trigger: "ai_run",
        input: { goal: "draft_email", lead_id: "lead-1", actor_user_id: USER.id },
        output: null,
        trace_id: "trace-1",
        idempotency_key: null,
        error: null,
        started_at: null,
        finished_at: null,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      })
    );

    const result = await runBrain({ goal: "draft_email", leadId: "lead-1", channel: "email" });

    expect(result.id).toBe("run-123");
    expect(result.status).toBe("queued");
    expect(result.trigger).toBe("ai_run");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/ai/run");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"goal":"draft_email"');
  });

  it("getAICapabilities GETs the non-secret capability surface and parses every boolean", async () => {
    setSession({
      accessToken: "access-123",
      expiresIn: 3600,
      user: USER,
    });
    fetchMock.mockResolvedValue(
      jsonResponse({
        agent_runtime_enabled: false,
        founder_assistant_enabled: true,
        intelligence_triage_enabled: false,
        intelligence_narrative_enabled: true,
        ai_execution_enabled: false,
        ai_budget_configured: true,
      })
    );

    const capabilities = await getAICapabilities();

    expect(capabilities).toEqual({
      agent_runtime_enabled: false,
      founder_assistant_enabled: true,
      intelligence_triage_enabled: false,
      intelligence_narrative_enabled: true,
      ai_execution_enabled: false,
      ai_budget_configured: true,
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/ai/capabilities");
    expect(init.method).toBeUndefined();
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-123");
  });

  it("getAgentRun GETs a single run by id", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "run-123",
        organization_id: USER.organization_id,
        agent_name: "ai_brain",
        status: "running",
        trigger: "ai_run",
        input: {},
        cost: 0,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      })
    );

    const run = await getAgentRun("run-123");

    expect(run.id).toBe("run-123");
    expect(run.status).toBe("running");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/agents/runs/run-123");
    expect(init.method).toBeUndefined();
  });

  it("cancelAgentRun POSTs to the run cancel endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "run-123",
        organization_id: USER.organization_id,
        agent_name: "ai_brain",
        status: "cancelled",
        trigger: "ai_run",
        input: {},
        cost: 0,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      })
    );

    const run = await cancelAgentRun("run-123");

    expect(run.status).toBe("cancelled");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/agents/runs/run-123/cancel");
    expect(init.method).toBe("POST");
  });

  it("dispatchDraft POSTs the workflow payload", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ workflow: "outreach-dispatch", status: 200, data: {} })
    );

    const result = await dispatchDraft("outreach-dispatch", { lead_id: "lead-1" });

    expect(result.status).toBe(200);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.body as string) ?? "").toContain('"workflow":"outreach-dispatch"');
  });

  it("getAISettings GETs the effective settings", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        provider: "openai",
        model: "gpt-4o-mini",
        overridden: false,
        kill_switch: false,
      })
    );

    const settings = await getAISettings();

    expect(settings.provider).toBe("openai");
    expect(settings.overridden).toBe(false);
    expect(settings.kill_switch).toBe(false);
  });

  it("updateAISettings PATCHes the org override", async () => {
    setSession({
      accessToken: "access-123",
      expiresIn: 3600,
      user: USER,
    });
    fetchMock.mockResolvedValue(
      jsonResponse({ provider: "anthropic", model: "claude-3-5-sonnet", overridden: true })
    );

    const settings = await updateAISettings({ provider: "anthropic" });

    expect(settings.provider).toBe("anthropic");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("PATCH");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-123");
  });
});
