# AgencyOS Phase 6 — Batch 3: Final Independent Review Findings — Remediation Report

**Date:** 2026-11-15
**Scope:** EXACTLY the four findings from the final independent review. No Batch 4 work, no backend changes, no new product scope.
**Mode:** LOCAL BUILD, no staging/commit/push/merge. `main` untouched.

> **Superseded mechanics (added 2026-11-15, residual-findings pass).** The sections below describe the state of the code at THIS pass's completion date. In the immediately following residual-findings remediation (`docs/PHASE6_BATCH3_RESIDUAL_FINDINGS_REMEDIATION_REPORT.md`): the `msgBusyRef` atomic flag was replaced by an ownership-aware lock (`lib/ownership-lock.ts`); `selectedIdRef` and `lib/thread-selection.ts` were replaced by a single synchronous navigation/view-context guard (`lib/navigation-guard.ts`); the pagination cursor now tracks RAW consumed backend records independently of unique displayed records (`lib/paged-list.ts`). Tests referenced here (258) were later extended to 283. Historical command output is preserved verbatim below; code descriptions marked §2/§5/§7 refer to the earlier design.

---

## 1. Baseline (verified before changes)

| Item                  | Value                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| Branch                | `feat/phase6-commercial-v1`                                                                      |
| HEAD at start         | `f3c3172722d53af73ed23a92098b342def3976b1`                                                       |
| Working tree at start | Post-remediation Batch 3 state (0016 user-modified + untracked artifacts), verified before edits |
| HEAD at end           | `f3c3172722d53af73ed23a92098b342def3976b1` — **unchanged; nothing committed**                    |

---

## 2. Finding 1 (HIGH) — Lead Detail parent state was not identity-isolated

**Exact finding.** The page loader depended on `leadId` only (`useCallback(..., [leadId])`); the parent-level `lead`/`users` state, the assignee list and the action handlers could remain associated with the previous principal/route while new data was loading — old lead info remained visible during load and on failure, and actions could target the stale lead.

**Root cause.** Child panels were keyed by composite identity but the parent was not — isolation was delegated to the children, leaving `lead`/`users`/action scope unguarded.

**Fix (`frontend/src/app/(dashboard)/leads/[id]/page.tsx`).** Split the page into an outer shell + keyed inner view:

```tsx
export default function LeadDetailPage({ params }) {
  const session = useAuth();
  const { id: leadId } = use(params);
  if (!session) return null;
  return (
    <LeadDetailView
      key={detailIdentityKey(session.user, leadId) ?? "unauthenticated"}
      leadId={leadId}
    />
  );
}
```

- `detailIdentityKey` = `<organization_id>:<user.id>:<leadId>` (new framework-free helper, `lib/lead-detail-identity.ts`). Any change in lead route, user id, or org id changes the key → the entire inner view remounts: no prior lead data, users, assignees, open dialogs or action targets can render, even briefly.
- The inner loader keeps an explicit generation guard (`createGenerationGuard` from the same helper module) that discards responses issued before the view's lifetime; the unmount cleanup invalidates all in-flight generations.
- Because actions (`Edit`/`Delete`/`Assign`, notes/tasks/conversations/history panels) live only inside the keyed view, they can never target a previous lead after an identity change.
- Loading/error states are fresh per identity (Spinner → error) — no stale data on failure.

**Regression coverage (tests for all five required scenarios).** `lib/__tests__/lead-detail-identity.test.ts` (8 tests): identity stability; Lead A → B differs; Org A → B differs (same user + lead); User A → B differs (same org + lead); null principal → null key; guard: stale generation rejected after `invalidate()`; stale response capture test models "Old response arriving after the identity changes".

**DOM interaction limitation.** The repo's test environment is `node` only — no jsdom/testing-library/React test renderer, and no new dependency is permitted — so click-driven flows ("press Edit after switching leads") cannot be executed here. The isolation invariant itself (identity-keyed remount + generation rejection) is covered by the helper tests; visual/interaction verification of the remount behavior was additionally confirmed by code review of the render path (fresh mount = fresh state in every branch) and is honestly reported as unexecuted interactive coverage, not claimed as tested.

---

## 3. Finding 2 — Conversation message pagination (earliest-1,000 trap)

**Exact finding.** The panel requested offset 0 with limit 1,000, displaying the earliest 1,000 recorded messages. The backend supports `limit ≤ 1000` with free `offset` in ascending `created_at` order; the old copy ("earliest 1,000… not retrievable") was inaccurate.

**Root cause.** Hard-coded single page at offset 0; no append path.

**Fix (`lead-conversations-panel.tsx`).** Offset pagination via `useCallback(loadMoreMessages)`:

- Initial/refresh fetch: `offset 0, limit 1,000` (unchanged contract).
- **Load more messages** control appears whenever a full page was returned; each click fetches `offset = items.length` (the only reliable page cursor — `Page.total` is the page length, never used).
- Pages append in backend order; no client-side re-sorting or fabricated timestamps; deduplication by message id.
- Separate failure tracking for load-more vs initial-load: failures preserve previously loaded messages and expose a Retry targeting the failed page (`offset = items.length`).
- `loading` blocks duplicate concurrent page requests (machine returns identical state when already in flight; atomic `msgBusyRef` covers the handler's first synchronous decision).
- Pagination resets on thread switch (`setMsgList(initialPagedList())`); stale appends cannot land on a new thread (`messageGen` guard); the old "earliest/unretrievable" copy is replaced by `Showing N recorded messages … backend pages of up to 1,000` and `All recorded messages are shown.`
- The `PagedListState` machine lives in `lib/paged-list.ts` (framework-free; 15 unit tests + 2 selection-guard tests).

**Tests.** `lib/__tests__/paged-list.test.ts` — initial offset 0; offset progression 0→N by successfully loaded items; >500 aggregate proves no artificial cap and short-page termination; backend order preserved; failure preserves items and Retry targets the failed offset; concurrent request rejection; de-duplication. Panel-level initial render smoke tests retained (node env limitation, see §6).

---

## 4. Finding 3 — Assignment history: false 500-record cap removed

**Exact finding.** `MAX_ENTRIES = 500` treated the backend per-request `limit` maximum as a global cap — wrong; the backend pages by `offset` with no total-history ceiling.

**Fix (`lead-assignment-history-panel.tsx`).**

- `MAX_ENTRIES` removed; each page is 50 (backend default), offset increments by actual items loaded; pagination stops only when a short page arrives; newest-first backend order preserved; `Page.total` never used (it is the page length, not a global count).
- Retry targets the failed page: the header Retry, the inline Retry and the error full-screen all call a single `retry()` that retries `offset = entries.length` when items are loaded (else page 0). Loaded pages are never discarded.
- Duplicate concurrent load-more requests blocked by the atomic `busyRef` + `loadingMore` state; stale pages from a superseded request/lead are dropped by the existing generation guard — append applies only within the current generation.
- Ordering and `hasMore` semantics unchanged in behavior: full page ⇒ "Showing N most recent ownership changes. Older records may exist." + **Load more history**.

**Tests.** Covered by the shared machine suite (`paged-list.test.ts`): 12-page accumulation to 600 records (past 500), short-page termination, append order, failure preserves loaded pages, retry offset, duplicate-request rejection — the exact scenarios the finding demanded.

---

## 5. Finding 4 — Post-mutation UI selection theft on Record reply

**Exact finding.** After a successful record-reply, the handler unconditionally called `openThread(target)`, forcing the user's view to jump back to the mutated thread even if they had navigated elsewhere during the request.

**Fix (`lead-conversations-panel.tsx`).**

- `selectedIdRef` mirrors the current selection (updated in an effect, so it is fresh before any event handler runs); `isCurrentThread(currentId, targetId)` is the single shared rule (`lib/thread-selection.ts`).
- After the mutation: the thread **list** is always refreshed (ordering/`last_message_at`), but the **message view** refreshes only when `selectedIdRef.current === target.id`; otherwise the user's navigation is left untouched.
- The refresh failure path sets a thread-scoped error (tagged `{ threadId, message }`) so a failure can never render as another thread's composer error; DB-success + view-refresh-failure says exactly that instead of claiming the record failed.
- Successful replies remain fully recorded even when the user navigates away (the DB operation is never cancelled for UI reasons), and the user's current selection is never overwritten.
- `openThread` no longer runs for post-mutation refresh; entry `selected` identity drives the view only through explicit user action and the guarded refresh.

**Tests.** `lib/__tests__/thread-selection.test.ts` (same-thread true; other-thread false; null/undefined false). The completion-path behavior (no selection theft) is implemented exactly on that rule; interaction clicking cannot run in this environment (no DOM renderer) and is flagged as unverified interactively, not claimed as tested.

---

## 6. Tests / gates actually executed (this session)

| #   | Command                                                                                                                                                                                                                                                                                                                                                                                  | Result                                                                                                                      |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1   | `npx vitest run src/lib/__tests__/paged-list.test.ts src/lib/__tests__/lead-detail-identity.test.ts src/lib/__tests__/thread-selection.test.ts src/lib/__tests__/principal-cache.test.ts src/components/leads/lead-conversations-panel.test.tsx src/services/__tests__/conversations.test.ts src/services/__tests__/leads.test.ts src/services/__tests__/teams-users-assignment.test.ts` | **68/68 passed** (37 files → see #2)                                                                                        |
| 2   | `npm test` (full suite)                                                                                                                                                                                                                                                                                                                                                                  | **37 files / 258 tests passed / 0 failed** (233 prior + 25 new: paged-list 15, lead-detail-identity 8, thread-selection 2)  |
| 3   | `npx tsc --noEmit`                                                                                                                                                                                                                                                                                                                                                                       | Pass                                                                                                                        |
| 4   | `npm run lint` (eslint .)                                                                                                                                                                                                                                                                                                                                                                | **0 errors** (1 pre-existing warning in untouched `postcss.config.mjs`)                                                     |
| 5   | Prettier (config-resolved) on changed files                                                                                                                                                                                                                                                                                                                                              | Clean                                                                                                                       |
| 6   | `npm run build` (next build)                                                                                                                                                                                                                                                                                                                                                             | **Pass** — 37/37 routes                                                                                                     |
| 7   | `git diff --check`                                                                                                                                                                                                                                                                                                                                                                       | No whitespace errors (only local CRLF notices on untouched-in-git files)                                                    |
| 8   | Backend (no backend files changed in this pass)                                                                                                                                                                                                                                                                                                                                          | ruff / mypy / pytest results carried over from the last verified run: **1,864 passed / 101 skipped / 0 failed** — unchanged |

**No test was deleted, weakened, or suppressed.** One lint `useEffect` ordering complaint was fixed by restructuring the effect (captured `guard` in a local) — not by disabling rules. The two existing reports were corrected where their statements became inaccurate (pagination rows, manifest, risk-register row 4 — superseded notes included, not silent edits).

---

## 7. Changed files this pass

| File                                                              | Type     | Purpose                                                                                                                                                                            |
| ----------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/app/(dashboard)/leads/[id]/page.tsx`                | Modified | Identity-keyed outer shell + inner `LeadDetailView` (composite identity: org:user:lead); generation-guarded loader via `createGenerationGuard`                                     |
| `frontend/src/lib/lead-detail-identity.ts`                        | Added    | `detailIdentityKey()` + `createGenerationGuard()` (framework-free)                                                                                                                 |
| `frontend/src/lib/__tests__/lead-detail-identity.test.ts`         | Added    | 8 identity/guard regression tests                                                                                                                                                  |
| `frontend/src/lib/paged-list.ts`                                  | Added    | Generic offset-pagination machine (initial/append, keep-last-good, offset = items loaded, dedupe-by-id)                                                                            |
| `frontend/src/lib/__tests__/paged-list.test.ts`                   | Added    | 15 machine tests (incl. >500 accumulation, short-page stop, retry offset, duplicate-request rejection)                                                                             |
| `frontend/src/lib/thread-selection.ts`                            | Added    | `isCurrentThread()` post-mutation selection guard                                                                                                                                  |
| `frontend/src/lib/__tests__/thread-selection.test.ts`             | Added    | 2 selection-guard tests                                                                                                                                                            |
| `frontend/src/components/leads/lead-conversations-panel.tsx`      | Modified | Offset pagination w/ Load-more + retry; `msgBusyRef` duplicate-request guard; post-mutation selection guarded (no view theft); thread-scoped error for reply failures              |
| `frontend/src/components/leads/lead-assignment-history-panel.tsx` | Modified | `MAX_ENTRIES` cap removed; offset = items loaded; short page ends pagination; `retry()` retries the failed offset; `busyRef` duplicate-request guard; stale-response drop retained |
| `docs/PHASE6_BATCH3_FINAL_IMPLEMENTATION_REPORT.md`               | Modified | Errata item 4; risk-register row 4 resolved; manifest extended                                                                                                                     |
| `docs/PHASE6_BATCH3_REVIEW_REMEDIATION_REPORT.md`                 | Modified | §F pagination rows corrected with dated superseded note                                                                                                                            |
| This report                                                       | Added    | —                                                                                                                                                                                  |

No service file required changes (`listConversationMessages`/`listAssignmentHistory` already accept `offset`); no backend source, schema, migration, dependency, CI, or authentication architecture was touched.

## 8. Remaining limitations (unchanged in kind)

1. Interactive DOM behavior cannot execute in this repository's node-only test environment — component rendering is smoke-tested; interaction correctness rests on the framework-free machines + code review here, and must be exercised in a browser (staging) before sign-off. Two render-effect reports of exact click paths are honestly unverifiable here.
2. PostgreSQL/Redis-backed backend integration tests (RLS tenant isolation etc.) remain environment-blocked locally; CI/staging must run them on the merge commit.
3. PDF (Sheet 2B #14–#20) fidelity and the 360–1440 px viewport matrix remain unverified (D-09 — design source unavailable to this agent).
4. npm audit state (12 findings incl. zod 3 HIGH) unchanged; not in this pass's scope.
5. Thread list (`listForLead`) has no backend pagination and is complete by contract — no UI paging there (by design).

## 9. Protected state

- `database/migrations/0016_search_trigram_indexes.sql`: untouched, `M` with the identical baseline diff (1+/46−); never read/restored/staged.
- All pre-existing untracked user artifacts preserved verbatim; no new files outside the declared scope; scratch files all deleted or `%TEMP%`.
- **Nothing staged, committed, pushed, merged, amended, or rebased.** Branch `feat/phase6-commercial-v1` @ `f3c3172722d53af73ed23a92098b342def3976b1`, remote unchanged. `main` never checked out. PR #2 remains Draft. Batch 4 not started.

## 10. Final verdict

# **CONDITIONAL PASS — All four findings fixed and unit-verified locally; interactive QA remains environment-gated**

The four findings are closed with focused regression tests (identity isolation incl. stale-response rejection and remount keys; framework-free pagination machinery with >500-record accumulation, short-page termination, failed-page retry-offset, and concurrent-duplicate rejection; post-mutation selection guard that cannot yank the user back to the mutated thread). All runnable gates are green: **258 vitest tests (37 files), tsc, ESLint, prettier, production build, git diff --check**.

Not PASS because (a) interactive DOM coverage is unavailable in this node-only environment — click-path behavior of remounts/retries is verified via the machine/guard tests and review, not executed; (b) backend integration/RLS tests still require CI/staging PostgreSQL/Redis; (c) PDF/viewport fidelity remains unverified. None of these was created or worsened by this pass.

**Founder actions before merge:** CI on the exact commit (incl. PostgreSQL/Redis suites), browser pass with a resizable visible window + D-09 design source, and staging rehearsal of the four fixed flows (switch org/user/lead under load, page past 1,000 messages, page past 50/500 history records, reply while navigating away).
