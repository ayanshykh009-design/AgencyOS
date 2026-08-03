import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import { createNote, deleteNote, listNotesByLead, updateNote } from "@/services/notes";
import { globalSearch } from "@/services/search";
import { listAuditLogs } from "@/services/audit";
import type { Note, User } from "@/types";

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

describe("notes service", () => {
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

  it("listNotesByLead scopes to the lead", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0 }));

    await listNotesByLead("lead-1", 50);

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/notes?lead_id=lead-1&limit=50&offset=0");
  });

  it("createNote POSTs body and pin flag", async () => {
    const note: Note = {
      id: "55555555-5555-5555-5555-555555555555",
      organization_id: USER.organization_id,
      lead_id: "lead-1",
      author_user_id: USER.id,
      body: "Called back",
      pinned: true,
      created_at: "2026-08-02T00:00:00Z",
      updated_at: "2026-08-02T00:00:00Z",
    };
    fetchMock.mockResolvedValue(jsonResponse(note));

    const created = await createNote({ lead_id: "lead-1", body: "Called back", pinned: true });

    expect(created.pinned).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/notes");
    expect(init.method).toBe("POST");
    expect((init.body as string) ?? "").toContain('"pinned":true');
  });

  it("updateNote PATCHes pin state", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "n1", pinned: false }));

    await updateNote("n1", { pinned: false });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("PATCH");
    expect((init.body as string) ?? "").toContain('"pinned":false');
  });

  it("deleteNote issues a DELETE", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await deleteNote("n1");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/notes/n1");
    expect(init.method).toBe("DELETE");
  });
});

describe("search service", () => {
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

  it("globalSearch sends the query and limit", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        query: "acme",
        leads: [],
        tasks: [],
        notes: [],
        counts: { leads: 0, tasks: 0, notes: 0, total: 0 },
      })
    );

    const result = await globalSearch("acme", 5);

    expect(result.query).toBe("acme");
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/search?");
    expect(url).toContain("q=acme");
    expect(url).toContain("limit=5");
  });
});

describe("audit service", () => {
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

  it("listAuditLogs encodes filters", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listAuditLogs({ eventType: "lead_deleted", limit: 25 });

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/audit?");
    expect(url).toContain("event_type=lead_deleted");
    expect(url).toContain("limit=25");
  });
});
