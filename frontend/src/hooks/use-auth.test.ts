import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Session } from "@/lib/session";

const harness = vi.hoisted(() => ({
  calls: [] as Array<{
    subscribe: (listener: () => void) => () => void;
    getSnapshot: () => Session | null;
    getServerSnapshot: () => Session | null;
  }>,
}));

vi.mock("react", () => ({
  useSyncExternalStore: (
    subscribe: (listener: () => void) => () => void,
    getSnapshot: () => Session | null,
    getServerSnapshot: () => Session | null
  ) => {
    harness.calls.push({ subscribe, getSnapshot, getServerSnapshot });
    return getSnapshot();
  },
}));

import { useAuth } from "@/hooks/use-auth";
import { clearSession, setSession, subscribe } from "@/lib/session";

const SESSION = {
  accessToken: "synthetic-access-token",
  expiresIn: 3600,
  user: { id: "user-1", organization_id: "org-1", role: "owner" },
} as Session;

describe("useAuth external-store wiring", () => {
  beforeEach(() => {
    harness.calls.length = 0;
    clearSession();
  });

  it("uses a null server snapshot so SSR and hydration markup agree", () => {
    expect(useAuth()).toBeNull();
    expect(harness.calls[0].getServerSnapshot()).toBeNull();
    expect(harness.calls[0].subscribe).toBe(subscribe);
  });

  it("reads the latest session even when refresh completed before subscription", () => {
    setSession(SESSION);
    expect(useAuth()).toEqual(SESSION);
    expect(harness.calls[0].getSnapshot()).toEqual(SESSION);
  });
});
