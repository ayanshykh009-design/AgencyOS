import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  acceptInvite,
  createInvite,
  listInvites,
  lookupInvite,
  revokeInvite,
} from "@/services/teams";
import { getUser, listUsers, updateUser } from "@/services/users";
import {
  assignLead,
  assignUnassignedLeads,
  getAssignmentRule,
  upsertAssignmentRule,
} from "@/services/assignment";
import type { TeamInvite, User } from "@/types";

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

const INVITE: TeamInvite = {
  id: "66666666-6666-6666-6666-666666666666",
  organization_id: USER.organization_id,
  email: "new@example.com",
  full_name: null,
  role: "member",
  status: "pending",
  invited_by_user_id: USER.id,
  expires_at: "2026-08-10T00:00:00Z",
  accepted_at: null,
  accepted_user_id: null,
  revoked_at: null,
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("teams service", () => {
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

  it("createInvite POSTs and returns the invite URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...INVITE, invite_url: "https://app/accept/tok" }));

    const created = await createInvite({ email: "new@example.com", role: "member" });

    expect(created.invite_url).toBe("https://app/accept/tok");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/teams");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"email":"new@example.com"');
  });

  it("listInvites GETs the paginated invites", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [INVITE], total: 1 }));

    const page = await listInvites(50, 0);

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/teams?limit=50&offset=0");
  });

  it("revokeInvite POSTs the revoke action", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...INVITE, status: "revoked" }));

    const invite = await revokeInvite(INVITE.id);

    expect(invite.status).toBe("revoked");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
  });

  it("lookupInvite uses a public (unauthenticated) request", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        email: "new@example.com",
        full_name: null,
        role: "member",
        organization_name: "Acme",
      })
    );

    const lookup = await lookupInvite("token-1");

    expect(lookup.organization_name).toBe("Acme");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/teams/public/token-1");
    expect(init.headers).not.toHaveProperty("Authorization");
  });

  it("acceptInvite uses a public POST", async () => {
    fetchMock.mockResolvedValue(jsonResponse(INVITE));

    await acceptInvite({ token: "token-1", full_name: "New", password: "secret" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/teams/accept");
    expect(init.method).toBe("POST");
    expect(init.headers).not.toHaveProperty("Authorization");
  });
});

describe("users service", () => {
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

  it("listUsers GETs the org members", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [USER], total: 1 }));

    const page = await listUsers(10, 0);

    expect(page.items).toHaveLength(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/users?limit=10&offset=0");
  });

  it("getUser fetches a single member", async () => {
    fetchMock.mockResolvedValue(jsonResponse(USER));

    const user = await getUser(USER.id);

    expect(user.id).toBe(USER.id);
  });

  it("updateUser PATCHes role and status", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...USER, role: "admin" }));

    await updateUser(USER.id, { role: "admin", is_active: true });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("PATCH");
    const body = (init.body as string) ?? "";
    expect(body).toContain('"role":"admin"');
    expect(body).toContain('"is_active":true');
  });
});

describe("assignment service", () => {
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

  it("getAssignmentRule returns null when none exists", async () => {
    fetchMock.mockResolvedValue(jsonResponse(null));

    const rule = await getAssignmentRule();

    expect(rule).toBeNull();
  });

  it("upsertAssignmentRule PUTs the rule", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "r1",
        organization_id: USER.organization_id,
        name: "Round robin",
        strategy: "round_robin",
        enabled: true,
        target_user_ids: [USER.id],
        conditions: {},
        last_assigned_index: 0,
        created_at: "2026-08-02T00:00:00Z",
        updated_at: "2026-08-02T00:00:00Z",
      })
    );

    const rule = await upsertAssignmentRule({
      name: "Round robin",
      strategy: "round_robin",
      enabled: true,
      target_user_ids: [USER.id],
    });

    expect(rule.strategy).toBe("round_robin");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/assignment/rules");
    expect(init.method).toBe("PUT");
  });

  it("assignUnassignedLeads POSTs the sweep", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ assigned: 3 }));

    const result = await assignUnassignedLeads();

    expect(result.assigned).toBe(3);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/assignment/assign-unassigned");
    expect(init.method).toBe("POST");
  });

  it("assignLead POSTs the assignment target", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "lead-1", owner_user_id: USER.id }));

    await assignLead("lead-1", { user_id: USER.id });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/assignment/leads/lead-1/assign");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain(`"user_id":"${USER.id}"`);
  });
});
