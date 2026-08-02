// Auth / routing middleware (Next 16 renamed `middleware` -> `proxy`).
//
// The backend owns real authentication (JWT validation). Here we only route:
// unauthenticated visitors to the (dashboard) route group are redirected to
// /login, and signed-in users visiting /login are bounced to /dashboard.
// The "is authenticated" signal is the short-lived cookie marker written by
// src/lib/session.ts — it never carries the token itself.

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
  // Protected route group + the login page (for the signed-in bounce).
  matcher: ["/(dashboard)/:path*", "/login/:path*"],
};
