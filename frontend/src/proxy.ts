// Auth / routing middleware (Next 16 renamed `middleware` -> `proxy`).
//
// The backend owns real authentication (JWT validation). Here we only route:
// unauthenticated visitors to the (dashboard) route group are redirected to
// /login, and signed-in users visiting /login are bounced to /dashboard.
// The "is authenticated" signal is the short-lived cookie marker written by
// src/lib/session.ts — it never carries the token itself. The marker is a
// routing hint only, never an authorization decision; the backend JWT check
// remains the source of truth for authentication and authorization.
//
// Matcher: Next.js route-group segments (like "(dashboard)") never appear in
// request URLs, so every protected family must be enumerated by its public
// URL prefix below. `/prefix/:path*` covers the bare prefix and all nested
// paths (path-to-regexp: `*` is zero or more). The array must stay a literal
// (statically analyzable) constant — matcher values from variables are
// ignored at build time. `src/proxy.test.ts` asserts this list stays in sync
// with the real route tree under src/app/(dashboard).

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ROUTES } from "@/lib/constants";
import { AUTH_COOKIE } from "@/lib/session";

export function proxy(request: NextRequest) {
  const authenticated = Boolean(request.cookies.get(AUTH_COOKIE)?.value);
  const { pathname } = request.nextUrl;

  const isLoginRoute = pathname === ROUTES.login || pathname.startsWith(`${ROUTES.login}/`);
  if (isLoginRoute) {
    if (authenticated) {
      return NextResponse.redirect(new URL(ROUTES.dashboard, request.url));
    }
    return NextResponse.next();
  }

  if (!authenticated) {
    const url = new URL(ROUTES.login, request.url);
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Protected route families (derived from src/app/(dashboard)/** — 20
  // top-level URL namespaces) + the login page (for the signed-in bounce).
  matcher: [
    "/dashboard/:path*",
    "/leads/:path*",
    "/pipeline/:path*",
    "/tasks/:path*",
    "/search/:path*",
    "/audit/:path*",
    "/team/:path*",
    "/assignment/:path*",
    "/ai/:path*",
    "/workflows/:path*",
    "/triggers/:path*",
    "/executions/:path*",
    "/credentials/:path*",
    "/deliveries/:path*",
    "/inbox/:path*",
    "/growth/:path*",
    "/founder/:path*",
    "/operational-monitoring/:path*",
    "/worker-monitoring/:path*",
    "/settings/:path*",
    "/login/:path*",
  ],
};
