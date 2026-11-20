// Framework-free synchronous navigation/view-context guard.
//
// This is the SINGLE mechanism the conversations panel uses to decide whether
// the user is still in the same view a mutation started in. It is deliberately
// not tied to React: navigation bumps a monotonic generation synchronously, so
// any async completion can compare contexts without waiting for effects.
//
// Every explicit navigation action bumps the generation:
//   navigateList()    — user returns to the thread list
//   navigateThread()  — user opens/switches to a thread
export type NavigationView = "list" | string; // "list" or a thread id

export interface NavigationToken {
  /** Monotonic generation captured at request time. */
  generation: number;
  /** View captured at request time. */
  view: NavigationView;
}

export interface NavigationGuard {
  /** Current context as a token for a mutation to capture. */
  capture(): NavigationToken;
  /** Current view. */
  view(): NavigationView;
  /** Navigate to the thread list (bumps generation). */
  navigateList(): NavigationToken;
  /** Navigate to a thread (bumps generation). */
  navigateThread(threadId: string): NavigationToken;
  /** True only if no navigation occurred since the token was captured. */
  isCurrent(token: NavigationToken): boolean;
  /** True only if the user is STILL on the same thread at the same generation. */
  isThread(token: NavigationToken, threadId: string): boolean;
  /** True only if the user is still on the LIST at the same generation. */
  isList(token: NavigationToken): boolean;
  /** Invalidate all captured tokens (unmount/lead change) without changing the view. */
  invalidate(): void;
}

export function createNavigationGuard(): NavigationGuard {
  let generation = 0;
  let currentView: NavigationView = "list";

  const snapshot = (): NavigationToken => ({ generation, view: currentView });

  const navigate = (view: NavigationView): NavigationToken => {
    generation += 1;
    currentView = view;
    return snapshot();
  };

  return {
    capture: () => snapshot(),
    view: () => currentView,
    navigateList: () => navigate("list"),
    navigateThread: (threadId: string) => navigate(threadId),
    isCurrent: (token) => token.generation === generation,
    isThread: (token, threadId) => token.generation === generation && token.view === threadId,
    isList: (token) => token.generation === generation && token.view === "list",
    invalidate: () => {
      generation += 1;
    },
  };
}
