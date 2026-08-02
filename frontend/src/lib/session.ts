// Client auth session store.
//
// Owns the JWT token pair + user profile and persists it to localStorage.
// A short-lived cookie marker is also set so Next.js middleware can route
// unauthenticated visitors to /login (the cookie never carries the token).
//
// This module is framework-free (no React, no fetch) so it is unit-testable
// in node. The React hook lives in src/hooks/use-auth.ts; API calls go through
// src/lib/api-client.ts.

import { STORAGE_KEYS } from "@/lib/constants";
import type { User } from "@/types";

export interface Session {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: User;
}

/** Cookie marker consumed by src/middleware.ts. */
export const AUTH_COOKIE = "agencyos.auth";
/** Keep the middleware marker aligned with the refresh-token lifetime. */
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

type Listener = () => void;

const listeners = new Set<Listener>();
let cachedSession: Session | null = null;

/** Read the persisted session from localStorage (cached in memory). */
export function getSession(): Session | null {
  if (cachedSession) {
    return cachedSession;
  }
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(STORAGE_KEYS.authSession);
  if (!raw) {
    return null;
  }
  try {
    cachedSession = JSON.parse(raw) as Session;
  } catch {
    window.localStorage.removeItem(STORAGE_KEYS.authSession);
    cachedSession = null;
  }
  return cachedSession;
}

export function getAccessToken(): string | null {
  return getSession()?.accessToken ?? null;
}

export function isAuthenticated(): boolean {
  return getSession() !== null;
}

/** Persist a new session (localStorage + middleware cookie) and notify. */
export function setSession(session: Session): void {
  cachedSession = session;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEYS.authSession, JSON.stringify(session));
  }
  setAuthCookie("1");
  notify();
}

/** Clear the session and its marker cookie. */
export function clearSession(): void {
  cachedSession = null;
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(STORAGE_KEYS.authSession);
  }
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
  const expires = value
    ? `; max-age=${COOKIE_MAX_AGE}; samesite=lax; path=/`
    : "; max-age=0; path=/";
  document.cookie = `${AUTH_COOKIE}=${value ?? ""}${expires}`;
}
