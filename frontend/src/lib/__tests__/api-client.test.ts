import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api-client";
import { clearSession, setSession } from "@/lib/session";
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

describe("apiFetch", () => {
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

  it("calls the API base URL and returns parsed JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ total: 7 }));
    const data = await apiFetch<{ total: number }>("/leads");

    expect(data.total).toBe(7);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/v1/leads");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("attaches the bearer token from the session", async () => {
    setSession({
      accessToken: "access-123",
      refreshToken: "refresh-456",
      expiresIn: 3600,
      user: USER,
    });
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await apiFetch("/dashboard/summary");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-123");
  });

  it("omits the bearer token when auth is disabled", async () => {
    setSession({
      accessToken: "access-123",
      refreshToken: "refresh-456",
      expiresIn: 3600,
      user: USER,
    });
    fetchMock.mockResolvedValue(jsonResponse({ access_token: "x" }));

    await apiFetch("/auth/login", { method: "POST", auth: false, body: "{}" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("parses the backend error envelope into ApiRequestError", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "lead.duplicate", message: "A lead already exists" } }, 409)
    );

    await expect(apiFetch("/leads")).rejects.toMatchObject({
      status: 409,
      code: "lead.duplicate",
      message: "A lead already exists",
    });
  });

  it("rejects with a generic error when the body is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("oops", { status: 500 }));

    await expect(apiFetch("/leads")).rejects.toMatchObject({
      status: 500,
      code: "request.failed",
    });
  });

  it("resolves undefined for 204 responses", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(apiFetch<void>("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("maps network failures to a network.error", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    await expect(apiFetch("/leads")).rejects.toMatchObject({
      status: 0,
      code: "network.error",
    });
  });
});
