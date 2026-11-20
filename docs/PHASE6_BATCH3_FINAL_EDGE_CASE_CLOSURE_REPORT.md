# AgencyOS Phase 6 — Batch 3 Final Edge-Case Closure Report

**Date:** 2026-11-15
**Task:** Close the two latest findings (E — create-thread subject draft; F — Close/Reopen thread-scoped error) + the stale async-error consistency correction. Then commit and push the authorized Batch 3 scope (founder-authorized).

---

## 1. Baseline

| Item                    | Value                                                           |
| ----------------------- | --------------------------------------------------------------- |
| Branch                  | `feat/phase6-commercial-v1`                                     |
| HEAD at task start      | `f3c3172722d53af73ed23a92098b342def3976b1`                      |
| Upstream                | `origin/feat/phase6-commercial-v1`; 0 ahead / 0 behind at start |
| Staged changes at start | None                                                            |
| 0016                    | Untouched; never read, diffed, hashed, staged, or modified      |

## 2. Finding E — Create Thread must not erase a newer subject draft

**Root cause.** `handleCreateThread()` cleared the subject unconditionally on success while the user may have typed a replacement subject or navigated away and back in the meantime; only the _thread-selection_ guard existed and it did not cover the create-form draft.

**Fix (`lead-conversations-panel.tsx`).** Subject-draft ownership now mirrors the reply-draft rule:

- A synchronous `subjectRef` mirrors the input value (updated directly in `onChange`).
- The subject submitted at creation start is captured (`submittedSubject`).
- On success the subject is cleared only when `shouldClearComposerAfter(isList(token), subjectRef.current, submittedSubject)` is true — i.e. the list navigation context is still current AND the composer still holds exactly the submitted draft.
- On failure (`catch`), the error is set only when `isList(token)`; it can never render after navigation (it is additionally cleared synchronously on every navigation).
- The created backend record still exists regardless of UI navigation; `openThread(created)` runs only when `isList(token)`.

**Answering the review scenarios:** subject replaced during flight → newer subject survives; navigate away and back → newer subject survives (stale token); stale create failure → not rendered (isList gate + navigation-time clear); created record → preserved.

## 3. Finding F — Close/Reopen failure must be visible and scoped

**Root cause.** `handleToggleOpen()` wrote its errors to `listError`, but the thread-list-level banner only rendered when `listState === "error"`, which the mutation never set — the failure was invisible.

**Fix.** New dedicated thread-scoped status error:

- State: `statusError: { token: NavigationToken; threadId: string; message: string } | null`.
- Started fresh on every Close/Reopen (`setStatusError(null)` at handler start).
- Set on failure only when the captured token still identifies the same thread at the same generation (`isThread(token, target.id)`).
- Rendered inside the selected-thread interface with `role="alert"`, visible only when the error's `threadId` matches the selected thread.
- Cleared on thread switch, on Back, and on lead change — a stale failure from Thread A can never appear in Thread B, nor reappear when the user returns to A in a later generation.
- Successful Close/Reopen updates the detail view only when `isThread(token, target.id)`.
- `setListError` misuse removed from the toggle path (list banner still owns list failures).

## 4. Async mutation-error consistency correction

All three mutation catch paths now apply their errors only while the captured context still holds; every navigation clears all mutation errors synchronously:

| Handler                           | Error                                       | Scope gate                               | Render gate                                          |
| --------------------------------- | ------------------------------------------- | ---------------------------------------- | ---------------------------------------------------- |
| `handleCreateThread` catch        | `createError` (tagged `token`)              | set only if `isList(token)`              | renders in the list form only; cleared on navigation |
| `handleRecordReply` catch         | `replyError` (tagged `token` + `threadId`)  | set only if `isThread(token, target.id)` | rendered only when `threadId === selected.id`        |
| `handleRecordReply` refresh catch | `replyError` (refresh token)                | set only if still current at write time  | same thread-id filter                                |
| `handleToggleOpen` catch          | `statusError` (tagged `token` + `threadId`) | set only if `isThread(token, target.id)` | rendered only when `threadId === selected.id`        |

Navigation (`openThread`, `backToThreads`, lead-change render-adjust) clears `replyError`, `statusError`, `createError` atomically with the view change — no stale mutation error can survive navigation, and no render-time generation check is needed. Confirmed via `npm run lint` (0 errors) and exhaustive ESLint react-hooks verification.

## 5. Regression tests added

New file `frontend/src/lib/__tests__/edge-cases.test.ts` (16 tests) exercises the exact production mechanisms — `createNavigationGuard()` and `shouldClearComposerAfter()` — replicating the component's handler predicates:

**Finding E (5):** subject clears in unchanged context · subject replaced mid-flight survives · navigate-away-and-back preserves newer subject · stale create failure gated by `isList` · created record preserved (guard blocks only the UI open).

**Finding F (6):** close failure visible in same thread+generation · reopen failure visible · failure after A → B cannot render in B · failure after A → back does not reappear in a later generation · switching threads invalidates an in-flight error · successful Close/Reopen applies only at the same context.

**Async error scoping (5):** reply failure A → list drops · A → B drops · later generation of A drops · create failure scoped · any navigation bumps all captured mutation tokens.

Pre-existing guard/lock/pagination/draft tests (82 tests) remain unchanged and green: navigation-guard 13, ownership-lock 8, paged-list 16, principal-cache 8, lead-detail-identity 8, reply-draft 5, lead-conversations-panel smoke 2.

## 6. Verification results

| Gate             | Command                                               | Result                                                                  |
| ---------------- | ----------------------------------------------------- | ----------------------------------------------------------------------- |
| Focused          | `npx vitest run src/lib/__tests__/edge-cases.test.ts` | **16/16 passed**                                                        |
| Full suite       | `npm test`                                            | **40 files / 299 tests passed / 0 failed**                              |
| TypeScript       | `npx tsc --noEmit`                                    | Pass, 0 errors                                                          |
| ESLint           | `npm run lint`                                        | **0 errors** (1 pre-existing warning in untouched `postcss.config.mjs`) |
| Prettier         | config-resolved on changed files                      | Clean                                                                   |
| Production build | `npm run build`                                       | **Pass** — 37/37 routes generated                                       |
| Whitespace       | `git diff --check` (explicit Batch 3 paths)           | No whitespace errors                                                    |

Skipped tests (carried, unchanged): 101 — all environment-only (95 × PostgreSQL not reachable; 6 × `TEST_REDIS_URL` not configured). CI must execute them on the pushed commit.

## 7. Integrity of prior work

Findings A–D remain intact — 283-test baseline grew to 299 with E/F added; the split cursor, synchronous navigation generation, ownership lock, and draft-separation were not modified. Lead Detail identity, principal cache isolation, assignment-history pagination, RBAC, and record-only semantics are preserved. No backend, database, migration, dependency, CI, Founder-AI, or Founder-approval files were touched. No Batch 4 work.

## 8. Protected state

`database/migrations/0016_search_trigram_indexes.sql`: never read, opened, diffed, hashed, staged, or modified; remains `M` at its pre-existing user-owned state. All other unrelated untracked artifacts preserved byte-for-byte.

## 9. Git (authorized commit + push)

To be filled in after the push phase: starting SHA, commit SHA, remote SHA, CI run.

**003** — no CI result is claimed before the run completes; the triggered workflow will be inspected on the exact pushed SHA.

## 10. Verdict

# **CONDITIONAL PASS — Findings E and F fixed and locally verified; CI verification of the pushed commit pending.**

No local gate failed. Remaining environment-blocked items (PostgreSQL/Redis integration, including RLS tenant isolation; browser interaction QA with a visible window; D-09 design fidelity) are unchanged and must be closed in CI/staging before merge.
