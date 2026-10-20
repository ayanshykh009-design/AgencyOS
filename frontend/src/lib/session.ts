// Client auth session store.
//
// Owns the in-memory JWT access token + user profile (V5 Option B). The
// refresh token is never stored in JS-accessible storage; it lives in the
// HttpOnly ``agencyos.refresh`` cookie and is rotated via /auth/refresh.
// A short-lived cookie marker is still set so Next.js middleware can route
// unauthenticated visitors to /login (the cookie never carries the token).
//
// This module is framework-free (no React, no fetch) so it is unit-testable
// in node. The React hook lives in src/hooks/use-auth.ts; API calls go through
// src/lib/api-client.ts.

import { STORAGE_KEYS } from "@/lib/constants";
import type { User } from "@/types";

export interface Session {
  accessToken: string;
  expiresIn: number;
  user: User;
}

/** Cookie marker consumed by src/proxy.ts. */
export const AUTH_COOKIE = "agencyos.auth";
/** Keep the middleware marker aligned with the refresh-token lifetime. */
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

type Listener = () => void;

const listeners = new Set<Listener>();
let cachedSession: Session | null = null;

/** Read the in-memory session (no persistence). */
export function getSession(): Session | null {
  return cachedSession;
}

export function getAccessToken(): string | null {
  return cachedSession?.accessToken ?? null;
}

export function isAuthenticated(): boolean {
  return cachedSession !== null;
}

/** Install a new in-memory session and notify. */
export function setSession(session: Session): void {
  cachedSession = session;
  setAuthCookie("1");
  notify();
}

/** Clear the in-memory session and its marker cookie. */
export function clearSession(): void {
  cachedSession = null;
  setAuthCookie(null);
  notify();
}

/** Subscribe to session changes; returns an unsubscribe function. */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

function setAuthCookie(value: string | null): void {
  if (typeof document === "undefined") {
    return;
  }
  const secure =
    typeof location !== "undefined" && location.protocol === "https:" ? "; secure" : "";
  const expires = value
    ? `; max-age=${COOKIE_MAX_AGE}; samesite=lax; path=/${secure}`
    : "; max-age=0; path=/";
  document.cookie = `${AUTH_COOKIE}=${value ?? ""}${expires}`;
}
