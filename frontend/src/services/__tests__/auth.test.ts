import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, getSession, isAuthenticated, setSession } from "@/lib/session";
import { login, logout } from "@/services/auth";
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

describe("auth service", () => {
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

  it("login persists the session and returns the auth response", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "access-123",
          refresh_token: "refresh-456",
          token_type: "bearer",
          expires_in: 3600,
          user: USER,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const result = await login({ email: "owner@example.com", password: "S3cure!pass" });

    expect(result.access_token).toBe("access-123");
    expect(isAuthenticated()).toBe(true);
    expect(getSession()?.user.email).toBe("owner@example.com");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/auth/login");
    expect((init as RequestInit).method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("logout clears the session even when the API call fails", async () => {
    setAuthenticated();
    fetchMock.mockResolvedValue(new Response(null, { status: 500 }));

    await logout();

    expect(isAuthenticated()).toBe(false);
  });

  it("logout sends the auth header and clears the session", async () => {
    setAuthenticated();
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await logout();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-123");
    expect(isAuthenticated()).toBe(false);
  });

  function setAuthenticated() {
    setSession({
      accessToken: "access-123",
      refreshToken: "refresh-456",
      expiresIn: 3600,
      user: USER,
    });
  }
});
