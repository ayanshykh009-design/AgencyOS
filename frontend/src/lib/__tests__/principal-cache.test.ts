import { afterEach, describe, expect, it, vi } from "vitest";

import { principalKey, installPrincipalIsolation } from "@/lib/principal-cache";
import { clearSession, setSession } from "@/lib/session";
import type { User } from "@/types";

function makeUser(id: string, org: string, role: User["role"] = "member"): User {
  return {
    id,
    organization_id: org,
    email: `${id}@example.com`,
    full_name: id,
    role,
    is_active: true,
    last_login_at: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };
}

function makeSink() {
  return { clear: vi.fn() };
}

describe("principalKey", () => {
  afterEach(() => clearSession());

  it("returns null when signed out", () => {
    expect(principalKey()).toBeNull();
  });

  it("combines organization id and user id", () => {
    setSession({ accessToken: "a", expiresIn: 3600, user: makeUser("u1", "org1") });
    expect(principalKey()).toBe("org1:u1");
  });
});

describe("installPrincipalIsolation", () => {
  afterEach(() => clearSession());

  it("clears the sink when the user id changes within the same organization", () => {
    setSession({ accessToken: "a", expiresIn: 3600, user: makeUser("u1", "org1") });
    const sink = makeSink();
    installPrincipalIsolation(sink);

    setSession({ accessToken: "b", expiresIn: 3600, user: makeUser("u2", "org1") });

    expect(sink.clear).toHaveBeenCalledTimes(1);
  });

  it("clears the sink when the organization id changes for the same user", () => {
    setSession({ accessToken: "a", expiresIn: 3600, user: makeUser("u1", "org1") });
    const sink = makeSink();
    installPrincipalIsolation(sink);

    setSession({ accessToken: "c", expiresIn: 3600, user: makeUser("u1", "org2") });

    expect(sink.clear).toHaveBeenCalledTimes(1);
  });

  it("clears the sink on logout", () => {
    setSession({ accessToken: "a", expiresIn: 3600, user: makeUser("u1", "org1") });
    const sink = makeSink();
    installPrincipalIsolation(sink);

    clearSession();

    expect(sink.clear).toHaveBeenCalledTimes(1);
  });

  it("does NOT clear the sink for token rotation of the same principal", () => {
    setSession({ accessToken: "a", expiresIn: 3600, user: makeUser("u1", "org1") });
    const sink = makeSink();
    installPrincipalIsolation(sink);

    // Same user, same org, fresh token (refresh rotation).
    setSession({ accessToken: "d", expiresIn: 3600, user: makeUser("u1", "org1") });

    expect(sink.clear).not.toHaveBeenCalled();
  });

  it("does not clear twice across consecutive principal changes", () => {
    setSession({ accessToken: "a", expiresIn: 3600, user: makeUser("u1", "org1") });
    const sink = makeSink();
    installPrincipalIsolation(sink);

    setSession({ accessToken: "b", expiresIn: 3600, user: makeUser("u2", "org1") });
    clearSession();

    expect(sink.clear).toHaveBeenCalledTimes(2);
  });

  it("stops clearing after unsubscribe", () => {
    setSession({ accessToken: "a", expiresIn: 3600, user: makeUser("u1", "org1") });
    const sink = makeSink();
    const unsubscribe = installPrincipalIsolation(sink);

    unsubscribe();
    setSession({ accessToken: "b", expiresIn: 3600, user: makeUser("u2", "org1") });

    expect(sink.clear).not.toHaveBeenCalled();
  });
});
