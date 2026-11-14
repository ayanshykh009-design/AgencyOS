import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, getSession, isAuthenticated, setSession } from "@/lib/session";
import {
  EMAIL_VERIFICATION_DISABLED_DETAIL,
  PASSWORD_RESET_DISABLED_DETAIL,
  isEmailVerificationDisabled,
  isPasswordResetDisabled,
  login,
  logout,
  mfaVerify,
  refresh,
  register,
} from "@/services/auth";
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

  it("refresh rotates the stored token pair", async () => {
    setAuthenticated();
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "access-2",
          token_type: "bearer",
          expires_in: 3600,
          user: USER,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const result = await refresh();

    expect(result.access_token).toBe("access-2");
    expect(getSession()?.accessToken).toBe("access-2");
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/auth/refresh");
  });

  it("register posts to /auth/register, persists the session and carries no bearer header", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "access-reg",
          token_type: "bearer",
          expires_in: 3600,
          user: USER,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } }
      )
    );

    const result = await register({
      email: "Owner@Example.com",
      password: "S3cure!pass",
      fullName: "  Owner  ",
      organizationName: "  Northwind Studio  ",
      organizationSlug: "northwind",
    });

    expect(result.access_token).toBe("access-reg");
    expect(isAuthenticated()).toBe(true);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/auth/register");
    expect((init as RequestInit).method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({
      email: "Owner@Example.com",
      password: "S3cure!pass",
      full_name: "  Owner  ",
      organization_name: "  Northwind Studio  ",
      organization_slug: "northwind",
    });
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("register surfaces backend organization/email conflict codes untouched", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: "organization.slug_taken", message: "Slug is already in use" },
        }),
        { status: 409, headers: { "Content-Type": "application/json" } }
      )
    );

    const attempt = register({
      email: "owner@example.com",
      password: "S3cure!pass",
      fullName: "Owner",
      organizationName: "Northwind",
      organizationSlug: "northwind",
    });

    await expect(attempt).rejects.toMatchObject({ code: "organization.slug_taken" });
    expect(isAuthenticated()).toBe(false);
  });

  it("mfaVerify completes a challenge and persists the session like a login", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "access-mfa",
          token_type: "bearer",
          expires_in: 3600,
          user: USER,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const result = await mfaVerify("challenge-token", "123456");

    expect(result.access_token).toBe("access-mfa");
    expect(isAuthenticated()).toBe(true);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/auth/mfa/verify");
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ mfa_token: "challenge-token", code: "123456" });
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("never writes tokens to browser storage", async () => {
    const store: Record<string, string> = {};
    const localStub = {
      getItem: (key: string) => store[`local:${key}`] ?? null,
      setItem: (key: string, value: string) => {
        store[`local:${key}`] = value;
      },
      removeItem: (key: string) => {
        delete store[`local:${key}`];
      },
      clear: () => Object.keys(store).forEach((key) => delete store[key]),
      get length() {
        return Object.keys(store).filter((key) => key.startsWith("local:")).length;
      },
      key: () => null,
    };
    const sessionStub = {
      ...localStub,
      getItem: (key: string) => store[`session:${key}`] ?? null,
      setItem: (key: string, value: string) => {
        store[`session:${key}`] = value;
      },
    };
    vi.stubGlobal("localStorage", localStub);
    vi.stubGlobal("sessionStorage", sessionStub);

    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "access-123",
          token_type: "bearer",
          expires_in: 3600,
          user: USER,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    await login({ email: "owner@example.com", password: "S3cure!pass" });

    const leaked = Object.entries(store).filter(([key]) =>
      /access[-_]?token|refresh[-_]?token|agencyos\.refresh/i.test(key)
    );
    expect(leaked).toEqual([]);
    expect(localStub.length).toBe(0);
  });

  it("detects the backend feature-off signals for reset and verification", () => {
    expect(isPasswordResetDisabled(PASSWORD_RESET_DISABLED_DETAIL)).toBe(true);
    expect(isPasswordResetDisabled("If that account exists, a reset email was sent")).toBe(false);
    expect(isPasswordResetDisabled(undefined)).toBe(false);
    expect(isEmailVerificationDisabled(EMAIL_VERIFICATION_DISABLED_DETAIL)).toBe(true);
    expect(isEmailVerificationDisabled("Verification email sent")).toBe(false);
    expect(isEmailVerificationDisabled(null)).toBe(false);
  });

  function setAuthenticated() {
    setSession({
      accessToken: "access-123",
      expiresIn: 3600,
      user: USER,
    });
  }
});
