import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AUTH_COOKIE,
  clearSession,
  getAccessToken,
  getSession,
  isAuthenticated,
  setSession,
  subscribe,
} from "@/lib/session";
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

describe("session store", () => {
  beforeEach(() => {
    // Simulate a browser so localStorage + the middleware cookie exist.
    const storage = new Map<string, string>();
    let cookie = "";
    Object.defineProperty(globalThis, "window", {
      value: {
        localStorage: {
          getItem: (k: string) => storage.get(k) ?? null,
          setItem: (k: string, v: string) => {
            storage.set(k, v);
          },
          removeItem: (k: string) => {
            storage.delete(k);
          },
        },
      },
      configurable: true,
    });
    Object.defineProperty(globalThis, "document", {
      value: {
        set cookie(v: string) {
          cookie = v;
        },
        get cookie() {
          return cookie;
        },
      },
      configurable: true,
    });
    clearSession();
  });

  afterEach(() => {
    clearSession();
    // @ts-expect-error restoring a test-only global
    delete globalThis.window;
    // @ts-expect-error restoring a test-only global
    delete globalThis.document;
  });

  it("is unauthenticated before any session is stored", () => {
    expect(isAuthenticated()).toBe(false);
    expect(getAccessToken()).toBeNull();
    expect(getSession()).toBeNull();
  });

  it("persists a session to localStorage and sets the middleware cookie", () => {
    setSession({
      accessToken: "access-123",
      refreshToken: "refresh-456",
      expiresIn: 3600,
      user: USER,
    });

    expect(isAuthenticated()).toBe(true);
    expect(getAccessToken()).toBe("access-123");
    expect(getSession()?.user.email).toBe("owner@example.com");
    expect(globalThis.document.cookie).toContain(`${AUTH_COOKIE}=1`);
  });

  it("clearSession removes storage and the cookie marker", () => {
    setSession({
      accessToken: "access-123",
      refreshToken: "refresh-456",
      expiresIn: 3600,
      user: USER,
    });
    clearSession();

    expect(isAuthenticated()).toBe(false);
    expect(globalThis.document.cookie).toContain(`${AUTH_COOKIE}=`);
    expect(globalThis.document.cookie).not.toContain(`${AUTH_COOKIE}=1`);
  });

  it("notifies subscribers on session changes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribe(listener);

    setSession({
      accessToken: "access-123",
      refreshToken: "refresh-456",
      expiresIn: 3600,
      user: USER,
    });
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    clearSession();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("ignores corrupted persisted data", () => {
    globalThis.window.localStorage.setItem("agencyos.session", "{not json");
    expect(getSession()).toBeNull();
  });
});
