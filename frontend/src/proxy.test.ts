// Tests for the auth/routing proxy (src/proxy.ts).
//
// Two layers are covered on purpose:
// 1. Matcher configuration — proxy() can only protect a route if the static
//    matcher lets the proxy run for it. Next.js provides no stable runtime
//    matcher evaluator for unit tests (`next/experimental/testing/server`
//    requires the Next server runtime), so the actual imported config.matcher
//    is evaluated here against the documented path-to-regexp semantics for
//    the "/prefix/:path*" shape (Next 16 proxy.md, rules 3 and 5: `*` is
//    zero-or-more, patterns are anchored to the start of the path). The real
//    compiled matcher is additionally verified end-to-end against the dev
//    server (see the Phase 6 guard-fix verification runbook).
// 2. Routing behavior — the proxy() function itself: anonymous visitors to
//    protected routes are redirected to /login with a `next` parameter, the
//    session-presence marker passes requests through (it is a routing hint,
//    never an authorization decision), and authenticated visitors are bounced
//    off /login.
import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { config, proxy } from "./proxy";
import { AUTH_COOKIE } from "@/lib/session";

// The 20 top-level URL namespaces of the (dashboard) route group, derived
// from src/app/(dashboard)/**/page.tsx (route-group segments never appear in
// request URLs). Keep in sync with the matcher in src/proxy.ts.
const PROTECTED_FAMILIES = [
  "dashboard",
  "leads",
  "pipeline",
  "tasks",
  "search",
  "audit",
  "team",
  "assignment",
  "ai",
  "workflows",
  "triggers",
  "executions",
  "credentials",
  "deliveries",
  "inbox",
  "growth",
  "founder",
  "operational-monitoring",
  "worker-monitoring",
  "settings",
] as const;

// Public and authentication pages that must stay reachable without a session.
const PUBLIC_ROUTES = [
  "/",
  "/contact",
  "/demo",
  "/pricing",
  "/privacy",
  "/terms",
  "/signup",
  "/mfa",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
  "/invite/invite-token-123",
] as const;

const BASE_URL = "http://localhost:3000";

/** Evaluate a "/prefix/:path*" matcher entry against a pathname. */
function matcherMatches(entry: string, pathname: string): boolean {
  if (!entry.endsWith("/:path*")) {
    throw new Error(`unhandled matcher entry shape (update the helper): ${entry}`);
  }
  const prefix = entry.slice(0, -":path*".length - 1);
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function matcherPathIsProtected(pathname: string): boolean {
  const entries = config.matcher as string[];
  return entries.some((entry) => matcherMatches(entry, pathname));
}

function makeRequest(path: string, withMarker: boolean): NextRequest {
  return new NextRequest(`${BASE_URL}${path}`, {
    headers: withMarker ? { cookie: `${AUTH_COOKIE}=1` } : {},
  });
}

function loginRedirectFor(path: string): string {
  const url = new URL("/login", `${BASE_URL}${path}`);
  url.searchParams.set("next", path);
  return url.toString();
}

describe("proxy matcher configuration (static analysis shape)", () => {
  it("is a flat array of literal string entries (statically analyzable)", () => {
    expect(Array.isArray(config.matcher)).toBe(true);
    for (const entry of config.matcher) {
      expect(typeof entry).toBe("string");
      expect((entry as string).endsWith("/:path*")).toBe(true);
    }
  });

  it("covers every protected route family from the (dashboard) route group", () => {
    const entries = config.matcher as string[];
    for (const family of PROTECTED_FAMILIES) {
      expect(entries).toContain(`/${family}/:path*`);
    }
  });

  it("has no duplicate or unexpected entries beyond the protected families + /login", () => {
    const entries = config.matcher as string[];
    const expected = [
      ...PROTECTED_FAMILIES.map((family) => `/${family}/:path*`),
      "/login/:path*",
    ].sort();
    expect([...entries].sort()).toEqual(expected);
  });

  it("matcher covers bare prefixes and nested paths for protected families", () => {
    const bare = PROTECTED_FAMILIES.map((family) => `/${family}`);
    const nested = [
      "/leads/123",
      "/leads/123/conversations",
      "/workflows/123",
      "/founder/proposals",
      "/founder/intelligence",
      "/ai/settings",
      "/settings/security",
    ];
    for (const path of [...bare, ...nested]) {
      expect(matcherPathIsProtected(path)).toBe(true);
    }
  });

  it("matcher never matches public or auth routes", () => {
    for (const path of PUBLIC_ROUTES) {
      expect(matcherPathIsProtected(path)).toBe(false);
    }
    // /login is intentionally matched (to bounce authenticated users off it).
    expect(matcherPathIsProtected("/login")).toBe(true);
  });

  it("matcher never matches framework or static asset paths", () => {
    for (const path of [
      "/_next/static/chunks/main.js",
      "/_next/image?src=x",
      "/favicon.ico",
      "/robots.txt",
      "/sitemap.xml",
    ]) {
      expect(matcherPathIsProtected(path)).toBe(false);
    }
  });
});

describe("proxy routing behavior", () => {
  it("redirects anonymous visitors from every protected family to /login with next", () => {
    for (const family of PROTECTED_FAMILIES) {
      const res = proxy(makeRequest(`/${family}`, false));
      expect(res.status).toBe(307);
      expect(res.headers.get("location")).toBe(loginRedirectFor(`/${family}`));
    }
  });

  it("redirects anonymous visitors from nested protected paths to /login with next", () => {
    for (const path of [
      "/leads/123",
      "/workflows/123",
      "/founder/proposals",
      "/founder/intelligence",
      "/ai/settings",
      "/settings/security",
    ]) {
      const res = proxy(makeRequest(path, false));
      expect(res.status).toBe(307);
      expect(res.headers.get("location")).toBe(loginRedirectFor(path));
    }
  });

  it("passes requests through when the session-presence marker is set", () => {
    for (const family of PROTECTED_FAMILIES) {
      const res = proxy(makeRequest(`/${family}`, true));
      expect(res.headers.get("location")).toBeNull();
    }
  });

  it("bounces authenticated visitors from /login to /dashboard", () => {
    const res = proxy(makeRequest("/login", true));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe(`${BASE_URL}/dashboard`);
  });

  it("lets anonymous visitors reach /login", () => {
    const res = proxy(makeRequest("/login", false));
    expect(res.headers.get("location")).toBeNull();
  });
});
