// Framework-free identity/generation helpers for the Lead Detail parent and
// its children. Split out so the isolation rules are unit-testable without a
// DOM renderer (the repo's test environment is node-only).

export interface PrincipalIdentity {
  id: string;
  organization_id: string;
}

/**
 * Composite identity for Lead Detail state: authenticated user + organization
 * + route lead id. Any change invalidates every datum scoped to the previous
 * combination.
 */
export function detailIdentityKey(
  principal: PrincipalIdentity | null,
  leadId: string
): string | null {
  if (!principal) return null;
  return `${principal.organization_id}:${principal.id}:${leadId}`;
}

export interface GenerationGuard {
  /** Capture the current generation number; callers must compare on completion. */
  capture(): number;
  /** True only for the most recent captured generation. */
  isCurrent(token: number): boolean;
  /** Invalidate everything issued so far (route/principal change, unmount). */
  invalidate(): void;
}

export function createGenerationGuard(): GenerationGuard {
  let current = 0;
  return {
    capture: () => ++current,
    isCurrent: (token) => token === current,
    invalidate: () => {
      current += 1;
    },
  };
}
