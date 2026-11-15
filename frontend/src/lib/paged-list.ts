// Framework-free offset-pagination state machine shared by the assignment
// history and conversation message panes. No React, no fetching — pure
// transitions so every rule is unit-testable in the node test environment.
//
// Contract facts (backend):
// - pages are fetched with an explicit `limit`/`offset`; ordering is stable
//   (messages ascending by created_at; assignment history descending);
// - a response shorter than `pageSize` is the end of the collection;
// - `Page.total` is the length of the page, NOT a global match count — never
//   use it as a total;
// - the next page's offset is the number of RAW backend records consumed,
//   which is NOT necessarily the number of unique displayed records (pages can
//   repeat ids across boundaries).
export interface PagedListState<T> {
  /** Unique displayed records, in backend order (never re-sorted client-side). */
  items: T[];
  /**
   * Number of RAW backend records successfully consumed so far. This — not
   * `items.length` — is the offset for the next page. Advances by the raw
   * response length on every SUCCESSFUL response and never decreases.
   */
  consumed: number;
  /** True while a page request (initial or append) is in flight. */
  loading: boolean;
  /** Last failure message, or null. Previously loaded items AND the cursor are ALWAYS kept. */
  error: string | null;
  /** True while a full page was returned by the latest fetch (more may exist). */
  hasMore: boolean;
}

export function initialPagedList<T>(): PagedListState<T> {
  return { items: [], consumed: 0, loading: false, error: null, hasMore: true };
}

/** Offset for the next page request — the number of raw backend records consumed. */
export function nextOffset<T>(state: PagedListState<T>): number {
  return state.consumed;
}

/**
 * Begin a page request. Returns the SAME state object (no transition, no
 * request should be issued) when a request is already in flight — this is the
 * duplicate-concurrent-request guard.
 */
export function beginPage<T>(state: PagedListState<T>): PagedListState<T> {
  if (state.loading) return state;
  return { ...state, loading: true, error: null };
}

/**
 * Apply a successful page. `append: false` replaces (initial/refresh) and
 * re-baselines the cursor; `append: true` appends (load-more) and NEVER
 * reduces the cursor. Either way, the cursor advances by the raw response
 * length — before deduplication — so pages with repeated ids cannot skew it.
 */
export function applyPage<T extends { id: string }>(
  state: PagedListState<T>,
  page: T[],
  pageSize: number,
  append: boolean
): PagedListState<T> {
  const consumed = append ? state.consumed + page.length : page.length;
  const items = append ? dedupeById([...state.items, ...page]) : dedupeById([...page]);
  return {
    items,
    consumed,
    loading: false,
    error: null,
    hasMore: page.length >= pageSize,
  };
}

/** Record a page failure. Items AND the consumed cursor are preserved. */
export function applyPageError<T>(state: PagedListState<T>, message: string): PagedListState<T> {
  return { ...state, loading: false, error: message };
}

/** Reset the machine (thread/lead change) — items and cursor both return to zero state. */
export function resetPagedList<T>(): PagedListState<T> {
  return initialPagedList<T>();
}

function dedupeById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    out.push(item);
  }
  return out;
}
