// Framework-free ownership-aware request lock.
//
// Used for the conversation message "load more pages" request. The lock is
// held by ONE request at a time; only the owning request may release it. This
// prevents a stale request (threadswitched away, unmounted view, refreshed
// page) from releasing a lock acquired by a newer request.
//
// Token contract: callers pass a unique, monotonically increasing token per
// request (e.g. from the navigation guard generation). A stale token can
// never match the current owner.
export interface OwnershipLock {
  /** Acquire the lock for `token`. Returns true on success, false if already held. */
  tryAcquire(token: number): boolean;
  /** Release the lock only if `token` owns it. No-op otherwise. */
  release(token: number): void;
  /** Invalidate (force-release) whatever is held. Used on navigation/reset. */
  invalidate(): void;
  /** The current owner token, or null. */
  current(): number | null;
}

export function createOwnershipLock(): OwnershipLock {
  let owner: number | null = null;

  return {
    tryAcquire(token: number): boolean {
      if (owner !== null) return false; // a request is already in flight
      owner = token;
      return true;
    },
    release(token: number): void {
      if (owner === token) owner = null;
    },
    invalidate(): void {
      owner = null;
    },
    current: () => owner,
  };
}
