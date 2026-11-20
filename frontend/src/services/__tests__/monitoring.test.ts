import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, setSession } from "@/lib/session";
import { getDeliveryStatistics, getOperationalSummary } from "@/services/monitoring";
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

describe("monitoring service", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clearSession();
    setSession({ accessToken: "test-token", expiresIn: 3600, user: USER });
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearSession();
  });

  it("getDeliveryStatistics GETs /monitoring/delivery-statistics", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        queued: 1,
        processing: 2,
        retrying: 3,
        delivered: 4,
        failed: 5,
        cancelled: 6,
        active: 7,
        terminal: 8,
      })
    );

    const data = await getDeliveryStatistics();

    expect(data.delivered).toBe(4);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/monitoring/delivery-statistics");
  });

  it("getOperationalSummary GETs /monitoring/operational/summary", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ timestamp: "2026-08-01T00:00:00Z" }));

    await getOperationalSummary();

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/monitoring/operational/summary");
  });
});
