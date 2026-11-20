// Tenant/session isolation for the global React Query cache.
//
// The app mounts one global QueryClient (see app/providers.tsx). Cached reads
// must never survive a change of the authenticated principal — neither who the
// user is nor which organization they belong to — so the cache is scoped by a
// composite identity key and cleared whenever it changes (including logout).
//
// This module is framework-free; the wiring into React lives in providers.tsx.
import { getSession, subscribe } from "@/lib/session";

/**
 * Composite of the authenticated principal's identity as seen by the backend:
 * `<organization_id>:<user_id>`. Token rotation alone does NOT change the key.
 */
export function principalKey(): string | null {
  const session = getSession();
  if (!session) return null;
  return `${session.user.organization_id}:${session.user.id}`;
}

/** Minimal sink that the isolation helper can clear (satisfied by QueryClient). */
export interface PrincipalCacheSink {
  clear(): void;
}

/**
 * Clear `sink` whenever the authenticated principal identity changes — a
 * different user, a different organization, or logout. Returns the
 * unsubscribe function. The initial subscription never clears synchronously;
 * it only reacts to subsequent session changes.
 */
export function installPrincipalIsolation(sink: PrincipalCacheSink): () => void {
  let current = principalKey();
  return subscribe(() => {
    const next = principalKey();
    if (next !== current) {
      current = next;
      sink.clear();
    }
  });
}
