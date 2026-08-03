import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  checkDuplicates,
  createLead,
  deleteLead,
  getLead,
  listLeads,
  updateLead,
} from "@/services/leads";
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
  email_normalized: "ada@example.com",
  phone_normalized: null,
  website_domain: null,
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  deleted_at: null,
  first_name: "Ada",
  last_name: "Lovelace",
  company: "Analytical Engines",
  position: null,
  location: null,
  linkedin_url: null,
  email: "ada@example.com",
  phone: null,
  whatsapp: null,
  website: null,
  notes: null,
  status: "new",
  score: 60,
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

describe("leads service", () => {
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

  it("listLeads sends filters as query params", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [LEAD], total: 1 }));

    const page = await listLeads({
      status: "won",
      minScore: 50,
      sort: "created_at",
      order: "desc",
      limit: 10,
    });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/leads?");
    expect(url).toContain("status=won");
    expect(url).toContain("min_score=50");
    expect(url).toContain("limit=10");
    expect(url).toContain("sort=created_at");
    expect(url).toContain("order=desc");
  });

  it("listLeads omits empty filters", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0 }));

    await listLeads();

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/leads");
  });

  it("getLead fetches a single lead", async () => {
    fetchMock.mockResolvedValue(jsonResponse(LEAD));

    const lead = await getLead(LEAD.id);

    expect(lead.id).toBe(LEAD.id);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/leads/${LEAD.id}`);
  });

  it("createLead POSTs the payload with auth header", async () => {
    fetchMock.mockResolvedValue(jsonResponse(LEAD));

    const created = await createLead({ email: "ada@example.com", first_name: "Ada" });

    expect(created.id).toBe(LEAD.id);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/leads");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"email":"ada@example.com"');
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-123");
  });

  it("updateLead PATCHes partial fields", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...LEAD, status: "contacted" }));

    const updated = await updateLead(LEAD.id, { status: "contacted", score: 75 });

    expect(updated.status).toBe("contacted");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/leads/${LEAD.id}`);
    expect(init.method).toBe("PATCH");
    expect((init.body as string) ?? "").toContain('"status":"contacted"');
  });

  it("deleteLead issues a DELETE", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await deleteLead(LEAD.id);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/leads/${LEAD.id}`);
    expect(init.method).toBe("DELETE");
  });

  it("checkDuplicates queries by contact channels", async () => {
    fetchMock.mockResolvedValue(jsonResponse([LEAD]));

    const duplicates = await checkDuplicates({ email: "ada@example.com", phone: "555" });

    expect(duplicates).toHaveLength(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/leads/duplicates?");
    expect(url).toContain("email=ada%40example.com");
    expect(url).toContain("phone=555");
  });

  it("surfaces backend error envelope", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "lead.email_exists", message: "Email already exists" } }, 409)
    );

    await expect(createLead({ email: "dup@example.com" })).rejects.toThrow("Email already exists");
  });
});
