# AgencyOS Phase 6 — Batch 3: Residual Independent Review Findings — Remediation Report

**Date:** 2026-11-15
**Scope:** Exactly the four residual findings (A, B, C, D) from the latest independent source review. No Batch 4, no backend changes, no new product scope.
**Mode:** LOCAL BUILD, no staging/commit/push/merge. `main` untouched.

---

## 0. Baseline (verified before any change)

| Item                     | Value                                                                                                                   |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| Branch                   | `feat/phase6-commercial-v1`                                                                                             |
| HEAD at start = baseline | `f3c3172722d53af73ed23a92098b342def3976b1`                                                                              |
| Working tree at start    | Post-findings-pass state (0016 user-modified + untracked artifacts), verified                                           |
| HEAD at end              | `f3c3172722d53af73ed23a92098b342def3976b1` — **unchanged; nothing committed**                                           |
| 0016                     | Not opened, not read, not diffed, not hashed, not staged, not included in any export; `M` with identical baseline state |

## 1. Root causes and fixes

### Finding A — Pagination cursor conflated unique items with raw consumed records (HIGH-value correctness)

**Root cause.** `nextOffset()` derived the backend cursor from `state.items.length`, while `applyPage` deduplicated by id — so a page containing previously-seen ids advanced the cursor fewer times than records actually consumed, and a later page could be fetched at the wrong offset (records skipped/duplicated).

**Fix.** `lib/paged-list.ts` redesigned: `PagedListState` now carries **two independent values** — `items` (unique displayed records, backend order) and `consumed` (RAW backend records successfully consumed). Rules: initial cursor 0; every successful response advances `consumed` by the raw response length (before deduplication); a failed request never advances it; append can never reduce it; refresh re-baselines; short page → `hasMore=false`; full page → `hasMore=true`; `Page.total` never used. Both panels (conversations messages, assignment history) use or comply with the same cursor rules; the conversations panel now passes `offset = nextOffset(msgList)` which reads `consumed`.

**Tests** (`lib/__tests__/paged-list.test.ts`, rewritten — 16): initial 0; progression; **critical**: page 1 `[A,B]`, page 2 `[B,C]` → displayed `[A,B,C]`, next offset `4`; raw cursor advances by response length with duplicates; failed append preserves items + cursor; failed initial page leaves cursor 0; retry uses exact failed offset; short page terminates; full page keeps `hasMore`; >500-record accumulation; backend order preserved; append never reduces cursor; refresh re-baselines; boundary de-duplication; reset zeroes both; duplicate-request rejection (`beginPage` identity).

### Finding B — Selection protection incomplete across async mutations

**Root cause.** A single post-mutation rule existed for Record Reply; `handleCreateThread`, `handleToggleOpen`, `openThread` and `backToThreads` had no equivalent synchronous navigation context, and the panel relied on an effect-mirrored ref as its only selection truth.

**Fix.** New framework-free **synchronous navigation/view-context guard** (`lib/navigation-guard.ts`): every explicit navigation bumps a monotonic generation synchronously (`navigateList`/`navigateThread`), every async mutation captures a token at start; completion handling uses `isList`/`isThread`/`isCurrent`:

- **Record Reply** — list always refreshes; message view refreshes only when still on the same thread at the same generation; draft cleared only when the composer still holds the submitted draft (`reply-draft.ts`); thread-scoped errors (tagged `threadId`) can never surface in another thread.
- **Create Thread** — list refreshes; the new thread is opened only when `isList(token)` (user still on the list where the mutation started); the already-persisted record is retained either way.
- **Close/Reopen** — list refreshes; selected-thread details update only while `isThread(token, id)`; navigating away can no longer trigger a stale view selection.
- `openThread`/`backToThreads` update the guard synchronously; `reply` draft cleared on explicit thread switch or on return to list, but NOT on same-thread refresh and never for a newer draft typed after submission.
- `thread-selection.ts` (disconnected duplicate of the same rule) **removed**; the guard is the single mechanism, and its tests use it directly.

**Tests** (`lib/__tests__/navigation-guard.test.ts`, 13): same-thread stays applied; A→B switch blocked; return-to-list blocked; create-thread completion after user opened Thread B (no theft); close/reopen completion after navigating away; stale errors filtered by thread; A→B→A does NOT revive a stale token; mutations remain successful despite navigation; capture stability; `list→thread→list` generation cycles.

### Finding C — A stale request could release a newer pagination lock

**Root cause.** `loadMoreMessages()` did `msgBusyRef.current = false` unconditionally in `finally` — an old (stale) request could clear the lock owned by a newer request after thread switches/invalidation.

**Fix.** Ownership-aware lock (`lib/ownership-lock.ts`): each load-more request captures a token (the navigation guard's generation); the lock has a single owner; `.finally` releases only when the completing request owns it (`release(token)` no-ops otherwise); `openThread`, `backToThreads` and the unmount path call `lock.invalidate()` so navigation frees the stale request's lock, after which the new view's request may acquire immediately (Finding C test 3 and 7). Stale `.then/.catch/.finally` never mutate current state and never clear another request's lock.

**Tests** (`lib/__tests__/ownership-lock.test.ts`, 8): single owner; concurrent second rejected; invalidate releases; stale release cannot clear the new owner; stale repeated release no-op; current owner releases; failure releases own lock, retry reacquires; stale-failure-then-retry doesn't wedge.

### Finding D — Reply drafts crossed thread boundaries

**Root cause.** One shared `reply` string for the whole panel; cross-thread switch carried the draft; a late success could erase a newer draft.

**Fix.** Switching threads clears the draft (`if (!sameThread) setReply("")` in `openThread`); Back to list clears it; opening any thread starts from a clean composer when coming from a different thread/context; same-thread refresh preserves the draft; clearing after success happens only under `shouldClearComposerAfter(navigationMatches, currentDraft, submittedDraft)` — a late success cannot erase a draft typed afterwards; draft reset on leadId change also restored.

**Tests** (`lib/__tests__/reply-draft.test.ts`, 5): context match + same draft → clear; navigated away → keep; draft replaced → keep; newer unrelated draft → keep; both conditions required.

## 2. What was preserved (integration requirements)

- Conversations inside Lead Detail only; record-only delivery copy; backend authoritative for sender attribution and organization scope; LEAD_READ/LEAD_WRITE gates; loading/error/empty/ready distinctions; last-good preservation on refresh failure; retry behavior; assignment-history no-artificial-cap pagination (never regressed to the 500 cap); parent Lead Detail identity isolation (`detailIdentityKey` keyed remount + `createGenerationGuard`); principal cache isolation (`principal-cache.ts` + providers); no fake data, no new scope.

## 3. Files changed this pass

| File                                                         | Type                 | Why                                                                                                                             |
| ------------------------------------------------------------ | -------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/lib/paged-list.ts`                             | Modified             | Split cursor: `items` (unique) vs `consumed` (raw); correct offset semantics                                                    |
| `frontend/src/lib/__tests__/paged-list.test.ts`              | Modified (rewritten) | 16 tests incl. the required critical case (page 1 `[A,B]` / page 2 `[B,C]` → displayed `[A,B,C]`, next offset = 4)              |
| `frontend/src/lib/navigation-guard.ts`                       | Added                | Synchronous navigation/view-context guard (single source of navigation truth)                                                   |
| `frontend/src/lib/__tests__/navigation-guard.test.ts`        | Added                | 13 tests exercising the exact guard the component uses                                                                          |
| `frontend/src/lib/ownership-lock.ts`                         | Added                | Ownership-aware lock for the load-more request (Finding C)                                                                      |
| `frontend/src/lib/__tests__/ownership-lock.test.ts`          | Added                | 8 tests (acquire/concurrent/invalidate/stale-release)                                                                           |
| `frontend/src/lib/reply-draft.ts`                            | Added                | `shouldClearComposerAfter()` composer-draft rule used by the component                                                          |
| `frontend/src/lib/__tests__/reply-draft.test.ts`             | Added                | 5 draft-rule tests                                                                                                              |
| `frontend/src/lib/thread-selection.ts`                       | **Removed**          | Superseded by `navigation-guard.ts` (disconnected duplicate; replaced by guard-native tests — not deleted to force green)       |
| `frontend/src/lib/__tests__/thread-selection.test.ts`        | **Removed**          | Same (2 tests removed, +42 replacements net)                                                                                    |
| `frontend/src/components/leads/lead-conversations-panel.tsx` | Modified             | All four findings wired into the actual component (token-captured mutations, nav-stable drafts, lock ownership, machine cursor) |
| `docs/PHASE6_BATCH3_FINAL_IMPLEMENTATION_REPORT.md`          | Modified             | Manifest now lists current files; stale entries removed                                                                         |
| `docs/PHASE6_BATCH3_FINAL_REVIEW_FINDINGS_REPORT.md`         | Modified             | Added dated superseded note marking removed mechanisms                                                                          |
| This report                                                  | Added                | —                                                                                                                               |

No backend file, dependency, schema, migration, CI, config, or authentication-architecture element changed. No Batch 4 work.

## 4. Commands and results

| #   | Command                                          | Result                                                                                                                                                                                                                       |
| --- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `npx vitest run …10 targeted files`              | **93/93 passed**                                                                                                                                                                                                             |
| 2   | `npm test`                                       | **39 files / 283 tests passed / 0 failed** (code changes + new suites; net +25 over 258)                                                                                                                                     |
| 3   | `npx tsc --noEmit`                               | Pass, 0 errors                                                                                                                                                                                                               |
| 4   | `npm run lint`                                   | **0 errors**; 1 pre-existing warning (`postcss.config.mjs`, untouched)                                                                                                                                                       |
| 5   | `npm run build`                                  | **Pass** — 37/37 routes generated                                                                                                                                                                                            |
| 6   | Prettier (config-resolved) on changed files      | All clean                                                                                                                                                                                                                    |
| 7   | `git diff --check` (explicit Batch 3 paths only) | Clean (only local CRLF notices)                                                                                                                                                                                              |
| 8   | Backend (untouched this pass)                    | Prior verified run stands: ruff clean, mypy clean (355 files), pytest **1,864 passed / 101 skipped / 0 failed** (skips = PostgreSQL/Redis environment-only; integration suites incl. `tenant_isolation_rls` must pass in CI) |

## 5. Honest limitations

1. Interactive DOM behavior (click-driven remounts/navigations) cannot execute in this node-only environment — the guard/lock/draft rules are unit-tested framework-free AND wired into the component, but they are NOT equivalent to browser interaction coverage. Not claimed as such.
2. PostgreSQL/Redis integration tests remain environment-blocked locally; merge remains gated on CI/staging.
3. PDF/design fidelity and viewport matrix remain unverified (D-09).
4. `git diff --check` shows CRLF informational lines only (Windows autocrlf); they are not whitespace errors.

## 6. Protected state / final Git posture

- `database/migrations/0016_search_trigram_indexes.sql` — never read, opened, diffed, hashed, staged, restored, deleted, or included; `M` with the identical baseline state.
- All pre-existing user-owned untracked artifacts preserved verbatim. No file outside the change manifest was touched; no file was deleted except `thread-selection.ts` + its test (superseded, documented in §3).
- **Nothing staged, committed, pushed, merged, amended, rebased, or switched.** Branch `feat/phase6-commercial-v1` @ `f3c3172722d53af73ed23a92098b342def3976b1`, remote unchanged. `main` untouched. PR #2 remains Draft. Batch 4 not started.

## 7. Final verdict

# **CONDITIONAL PASS** — All four residual findings fixed and verified locally; interactive QA remains environment-gated.

- Finding A: **FIXED & TESTED** (split cursor; critical A,B/B,C case green; >500-record accumulation green).
- Finding B: **FIXED & TESTED** (synchronous navigation generation; every mutation context-checked; 13 guard tests against the exact mechanism used).
- Finding C: **FIXED & TESTED** (ownership-aware lock; stale release impossible; 8 lock tests).
- Finding D: **FIXED & TESTED** (per-context draft clearing with unchanged-draft predicate; 5 draft tests).

Evidence: 283/283 vitest, tsc clean, ESLint 0 errors, production build 37/37, Prettier clean on changed files, `git diff --check` clean. Remaining blockers are environment-gated (DOM/browser interaction coverage, PostgreSQL/Redis integration) plus D-09 (design source) — all must close before merge/sign-off.

**Founder actions:** CI on the exact merge commit (incl. integration suites); a visible-window browser pass for the four fixed flows; D-09 for design fidelity; then the final Batch 3 sign-off.
