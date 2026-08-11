import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import {
  getNotificationTypeCounts,
  getUnreadCount,
  listNotifications,
  markNotificationRead,
  setNotificationRead,
} from "@/services/notifications";
import type { Notification, User } from "@/types";

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

const NOTIFICATION: Notification = {
  id: "55555555-5555-5555-5555-555555555555",
  organization_id: USER.organization_id,
  user_id: USER.id,
  type: "workflow_event",
  title: "Execution failed",
  body: "Workflow run failed after 3 attempts.",
  action_url: "/executions",
  metadata: {},
  is_read: false,
  read_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("notifications service", () => {
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

  it("listNotifications encodes only_unread", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [NOTIFICATION], total: 1 }));

    const page = await listNotifications({ onlyUnread: true });

    expect(page.total).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("only_unread=true");
  });

  it("getUnreadCount hits the unread-count endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ count: 3 }));

    const result = await getUnreadCount();

    expect(result.count).toBe(3);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/notifications/unread-count");
  });

  it("getNotificationTypeCounts hits the counts endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ counts: { system: 1 } }));

    const result = await getNotificationTypeCounts();

    expect(result.counts.system).toBe(1);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/notifications/counts");
  });

  it("markNotificationRead POSTs to the read endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...NOTIFICATION, is_read: true }));

    const result = await markNotificationRead(NOTIFICATION.id);

    expect(result.is_read).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/notifications/${NOTIFICATION.id}/read`);
    expect(init.method).toBe("POST");
  });

  it("setNotificationRead PATCHes is_read", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...NOTIFICATION, is_read: false }));

    await setNotificationRead(NOTIFICATION.id, false);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(`/notifications/${NOTIFICATION.id}`);
    expect(init.method).toBe("PATCH");
    const body = (init.body as string) ?? "";
    expect(body).toContain('"is_read":false');
  });
});
