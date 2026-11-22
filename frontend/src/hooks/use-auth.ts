// React hook exposing the current auth session with reactive updates.
"use client";

import { useSyncExternalStore } from "react";

import { getSession, subscribe, type Session } from "@/lib/session";

/** Server and pre-hydration clients must agree that no session exists yet. */
function getServerSession(): null {
  return null;
}

export function useAuth(): Session | null {
  return useSyncExternalStore(subscribe, getSession, getServerSession);
}
