import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  createStage,
  deleteStage,
  getBoard,
  listCloseReasons,
  moveLead,
  reorderStages,
} from "@/services/pipeline";
import type { Lead, User } from "@/types";

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

const LEAD: Lead = {
  id: "33333333-3333-3333-3333-333333333333",
  organization_id: USER.organization_id,
  lead_source_id: null,
  owner_user_id: null,
  email_normalized: null,
  phone_normalized: null,
  website_domain: null,
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  deleted_at: null,
  first_name: "Ada",
  last_name: null,
  company: null,
  position: null,
  location: null,
  linkedin_url: null,
  email: "ada@example.com",
  phone: null,
  whatsapp: null,
  website: null,
  notes: null,
  status: "new",
  score: 10,
  stage_id: null,
  close_reason_id: null,
  deal_value: null,
  won_at: null,
  lost_at: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("pipeline service", () => {
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

  it("getBoard requests the Kanban with a stage limit", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ stage: { id: "s1" }, leads: [] }]));

    const board = await getBoard(30);

    expect(board).toHaveLength(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/pipeline/board?limit_per_stage=30");
  });

  it("createStage POSTs name and lifecycle", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "s1", name: "Qualified", lifecycle: "open" }));

    const stage = await createStage({ name: "Qualified", lifecycle: "open" });

    expect(stage.name).toBe("Qualified");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/pipeline/stages");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"name":"Qualified"');
  });

  it("reorderStages POSTs the ordered stage ids", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await reorderStages(["s2", "s1"]);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"stage_ids":["s2","s1"]');
  });

  it("listCloseReasons filters by lifecycle", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listCloseReasons("won");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/pipeline/close-reasons?lifecycle=won");
  });

  it("deleteStage issues a DELETE", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await deleteStage("s1");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/pipeline/stages/s1");
    expect(init.method).toBe("DELETE");
  });

  it("moveLead POSTs the target stage and optional close reason", async () => {
    fetchMock.mockResolvedValue(jsonResponse(LEAD));

    await moveLead(LEAD.id, { stage_id: "s2", close_reason_id: "r1" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/pipeline/leads/${LEAD.id}/stage`);
    expect(init.method).toBe("POST");
    const body = (init.body as string) ?? "";
    expect(body).toContain('"stage_id":"s2"');
    expect(body).toContain('"close_reason_id":"r1"');
  });
});
