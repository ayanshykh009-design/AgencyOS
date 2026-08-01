// Auth / routing middleware placeholder.
// Protect the (dashboard) route group once authentication is implemented —
// redirect unauthenticated users to /login via the session check.

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  // TODO: verify Supabase session; redirect to /login when missing.
  return NextResponse.next();
}

export const config = {
  // Apply to the protected route group only.
  matcher: ["/(dashboard)/:path*"],
};
