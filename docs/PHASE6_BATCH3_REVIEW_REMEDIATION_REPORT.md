# AgencyOS Phase 6 — Batch 3 Independent Review Remediation Report

**Date:** 2026-11-14
**Task:** BUILD + FIX + REGRESSION TESTS against the findings from the independent review of the Batch 3 export.
**Scope:** Frontend remediation only. No backend source, schema, migration, dependency, CI, or authentication-architecture changes. No staging, commit, push, or merge. Batch 4 not started.

---

## A. Baseline verification (before any change)

| Item                                                  | Value                                                                                                                                      |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Branch                                                | `feat/phase6-commercial-v1`                                                                                                                |
| HEAD at start (= baseline)                            | `f3c3172722d53af73ed23a92098b342def3976b1`                                                                                                 |
| HEAD at end                                           | `f3c3172722d53af73ed23a92098b342def3976b1` — **unchanged**                                                                                 |
| Working tree at start                                 | Baseline Batch 3 state (uncommitted Batch 3 implementation + user-owned `0016` modification + untracked artifacts) — verified before edits |
| `database/migrations/0016_search_trigram_indexes.sql` | Untouched (`M`, diff 1+/46−, identical to baseline; SHA never read/modified)                                                               |

## B. Changed files (and reasons)

| File                                                              | Type                        | Reason for change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------------------------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/components/leads/lead-conversations-panel.tsx`      | Modified                    | (1) Delivery-truthful copy (record-only, see C); (2) explicit loading/error/empty states with **Retry** for thread-list and message-history failures; (3) last successfully loaded data preserved on refresh failure; (4) async generation guards stop stale responses from overwriting the selected thread; (5) 1,000-message truncation disclosure (see F); (6) same-thread message refresh preserves loaded messages; switching threads drops them; (7) `selectedIdRef` removed (lint + correctness); per-lead reset via render-adjust pattern |
| `frontend/src/components/leads/lead-assignment-history-panel.tsx` | Added earlier; now Modified | Same error-model as conversations (Retry, keep previous pages, never empty-success-on-failure) + offset pagination with visible "Showing N most recent" disclosure and **Load more history** (see F)                                                                                                                                                                                                                                                                                                                                              |
| `frontend/src/app/providers.tsx`                                  | Modified                    | Cache isolation delegated to `lib/principal-cache.ts`; principal now composite `organization_id:user_id` (was `user.id` alone) — clears React Query cache on either identity component changing, including logout                                                                                                                                                                                                                                                                                                                                 |
| `frontend/src/lib/principal-cache.ts`                             | Added                       | `principalKey()` + `installPrincipalIsolation(sink)` — framework-free, testable composite-identity cache isolation                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `frontend/src/lib/__tests__/principal-cache.test.ts`              | Added                       | 8 regression tests: user change, org change, logout, token rotation (no-op), unsubscribe, repeated changes                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `frontend/src/app/(dashboard)/leads/[id]/page.tsx`                | Modified                    | Panels (Notes/Tasks/Conversations/Assignment history) now keyed by `user.id` + `organization_id` + `lead.id` — full remount on lead/principal change; page loader is generation-guarded so a slow stale response cannot overwrite the current lead                                                                                                                                                                                                                                                                                                |
| `docs/PHASE6_BATCH3_FINAL_IMPLEMENTATION_REPORT.md`               | Modified                    | Corrected test-count arithmetic (Errata section) and file manifest; added remediation pointers                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| This report                                                       | Added                       | —                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

**No other files were modified.** In particular: no backend files, no test deletion, no dependency, config, or CI change; pre-existing CRLF-style prettier warnings elsewhere were left untouched. `0016_search_trigram_indexes.sql` was not read into the remediation and remains byte-for-byte the baseline artifact.

## C. Conversation message delivery truthfulness (HIGH priority — fixed)

The backend `POST /conversations/{id}/messages` **records an AGENT message in AgencyOS; it dispatches nothing externally**. The UI previously implied sending would occur. Now:

- Panel-persistent notice: "Messages are recorded in AgencyOS only. Nothing here is sent to the lead through email, WhatsApp, or any external channel."
- Composer notice: "Recording a reply saves it to this thread in AgencyOS. It is not sent to the lead through any external channel."
- Action renamed: **"Send reply" → "Record reply"** (`Recording…` while pending; `aria-label="Record a message"`, placeholder "Record a message…").
- New-thread notice: "This records a new thread in AgencyOS for this lead. It does not create a conversation with any external provider, and no message is sent anywhere." Submit buttons read "Recording…/Start conversation" (button keeps the creation verb — but the supporting copy makes its effect unambiguous), and the empty-state copy says "Record the first message — it is saved in AgencyOS and is not sent anywhere externally."
- Thread list/subtitle uses "No messages recorded" rather than implying delivery.
- **No provider dispatch was added.** No email/WhatsApp/Telegram call exists anywhere in the panel or the conversations service; verified by reading the full call graph and by grep (see G).
- On V1, inbound LEAD messages cannot arrive (no trusted provider-ingress endpoint exists); the UI only ever offers the AGENT record path, which is the founder-approved contract.

### Pre-existing backend `external_id` ingestion risk — documented, not modified

`ConversationMessage` persists an `external_id` field with a dedup check and an idempotent re-insert guard in `record_inbound_lead_message`, but **no unique constraint** exists (there is an ordinary index only). Until a provider ingress connects, duplicate provider deliveries are protected only by the service-level lookup, and the documented "unique constraint required before trusted provider ingress" decision remains **open and unactioned** — by design; it belongs to the provider-ingress work, not to V1 remediation, and no backend change was authorized here. Any future provider-ingress implementation must treat this as a blocking prerequisite, not a detail.

## D. Error, empty, and retry states (fixed)

**`lead-conversations-panel.tsx`** — thread list and message history now each have three distinguishable UI states (`loading` / `error` / `ready`) plus the loaded-data flag:

| Situation                               | Rendered behavior                                                                                                                      |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Initial load in flight, nothing loaded  | Spinner                                                                                                                                |
| Request failed, nothing loaded          | Error text + **Retry** button (never the empty-success copy)                                                                           |
| Request failed, data was already loaded | List/messages stay rendered + red `role="alert"` banner naming the error + inline **Retry** (never replaced by "No conversations yet") |
| Success, zero records                   | "No conversations yet" / "No messages recorded yet" (only after a real successful response)                                            |
| Success, records                        | List / thread view                                                                                                                     |

Same pattern for the create error (`role="alert"` under the form) and the record-reply error (`role="alert"` above the composer actions).

**`lead-assignment-history-panel.tsx`** — identical distinguishable states: spinner → error+Retry (full-screen when empty, banner when data exists) → "No assignment changes" (first success only) → list. Retry re-issues the first page; previous pages are never blanked on failure.

## E. Async request and session isolation (fixed)

**Providers / cache (A):**

- New `lib/principal-cache.ts`: `principalKey()` = `<organization_id>:<user_id>`; `installPrincipalIsolation(queryClient)` subscribes to the session store and calls `queryClient.clear()` whenever the composite key changes — different user, different org, or logout (sign-out clears the marker cookie → `notify()` → clear). Token rotation of the same principal does **not** clear (correct — nothing about the tenant changed). 8 unit tests prove: user-switch clears, org-switch clears, logout clears, rotation no-ops, repeated changes clear repeatedly, unsubscribe stops clearing.

**Component-local state (B):**

- Lead Detail now passes `key={…user.id:org:leadId…}` into Notes/Tasks/Conversations/Assignment-history panels — switching lead or principal **remounts** the panels, so no prior list, thread list, message history, composer text, or assignee list can leak into the new context.
- Panels additionally reset their own state on `leadId` change via the render-time adjust pattern (`activeLeadId !== leadId`), so they stay safe even without the parent key.

**Async races (C):**

- Generation guards on both streams in each panel: every request captures `generationRef`'s value; `.then/.catch/.finally` apply results only when the captured generation is still current. Bumping generations on unmount invalidates everything issued by the unmounted view (no setState-after-unmount is possible — unmounted views perform no state transitions; their promise callbacks bail out at the generation check).
- Lazy `useCallback` closures over fresh `selected` (no stale `selected` in `retryMessages`/`openThread`).
- The lead-detail page loader is also generation-guarded; a slow `getLead(A)` can no longer overwrite lead B's state or `assignee`.
- No dependencies added (React Query + raw `useRef` counters only). `AbortSignal` was not used because the API client is request-response without a signal path in these callsites and generation guards give the same guarantee without changing service signatures.

**Evidence available in this environment:** principal-isolation logic is unit-tested (8 tests, real session store). Component-level interaction coverage (clicking retry, switching threads, switching leads) cannot be executed — the repo's test environment is `environment: "node"` with no jsdom/testing-library and no added dependency is allowed; the panel initial-render smoke tests remain the ceiling for component rendering here. Async safety is therefore verified by code review + the service-level race semantics (the guard pattern), **not** by simulated unmount/remount renders; flagged honestly as a coverage limitation, not claimed as tested.

## F. Pagination disclosure (fixed)

| Surface                  | Backend fact                                                                                                | Disclosure implemented                                                                                                                                                                                                                                                                                                                      |
| ------------------------ | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Conversation messages    | `limit ≤ 1000` (default 200), ascending `created_at`; `offset` from 0                                       | **Corrected 2026-11-15:** offset-paginated properly — initial page limit 1000 offset 0; **Load more messages** appends subsequent pages (offset = messages loaded) in backend order with de-duplication and retry-at-failed-offset; accurate "Showing N …" disclosure replaces the earlier incorrect "earliest-1,000/unretrievable" wording |
| Assignment history       | `Page(items, total=len(items))` — `total` is the page length, not a match count; ordering `created_at` desc | **Corrected 2026-11-15:** pages 50 via `offset` with no artificial total cap (the earlier "stops at 500" line was wrong — it misread the per-request `limit` max as a total cap). Continuing while a full page returns; stops on a short page; **Load more history** remains; `Page.total` never used                                       |
| Conversation thread list | `listForLead` has no limit parameter — complete by contract                                                 | No limitation notice required; complete list always shown                                                                                                                                                                                                                                                                                   |
| Error semantics          | Any fetch failure keeps already-loaded pages visible with Retry — no silent truncation                      | Covered above                                                                                                                                                                                                                                                                                                                               |

> Superseded note (2026-11-15): the original §F table claimed threads over 1,000 showed "the earliest 1,000 … not retrievable" and that assignment history "stops at the 500-item backend parameter maximum". Both were inaccurate — conversation messages support proper offset pagination, and the 500 was a misread per-request limit. Both panels now page correctly; see `docs/PHASE6_BATCH3_FINAL_REVIEW_FINDINGS_REPORT.md`.

**No API contracts, limits, or schemas were changed.** `listAssignmentHistory` previously fetched limit 50 with no disclosure; it now pages with `offset`.

## G. Security contracts (unchanged, verified)

Verified in the built code and in the test suite:

- Continues sending legacy-required fields: `organization_id` (leads `createLead`, conversation create and message create), `conversation_id` and `sender_type: "agent"` (message create). These are the backend-mandated presence markers; the server overwrites `organization_id` with the authenticated principal and validates `sender_type` (only `"agent"` accepted) before any database work.
- Frontend grep against `frontend/src` confirms the ordinary-message payload never carries `sender_user_id`, `sent_at`, `external_id`, or arbitrary `metadata` — verified by source inspection and by an assertion-level test (`conversations.test.ts` "addConversationMessage … never sends sender identity fields"). Non-AGENT messages cannot be produced by this UI; the backend rejects them with 403 regardless.
- Server overrides tenant identity on every endpoint (verified in endpoint sources: `data["organization_id"] = current_user.organization_id` before reaching services); server sets `sender_user_id = actor.id` and `sent_at = utcnow()` in `add_message`.
- No LEAD inbound route added; `ConversationService.record_inbound_lead_message` remains unreachable from routers (structural guard test passes: `tests/api/test_conversations_rbac.py::test_no_router_references_the_trusted_inbound_path`).
- No `external_id` migration or constraint was added; the pre-existing ingestion risk is documented in section C as a future provider-ingress prerequisite.

## H. Regression results (all rerun this session)

| #   | Command                                                                                                                                            | Result                                                                                                                                        |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `npx vitest run` (full suite)                                                                                                                      | **34 files / 233 tests passed / 0 failed**                                                                                                    |
| 2   | `npx vitest run …conversations.test.ts …lead-conversations-panel.test.tsx …teams-users-assignment.test.ts …leads.test.ts …principal-cache.test.ts` | **43/43 passed** (conversations service 11, panel smoke 2, assignment-history 2 within teams-users-assignment 14, leads 8, principal-cache 8) |
| 3   | `npx tsc --noEmit`                                                                                                                                 | Pass, 0 errors                                                                                                                                |
| 4   | `npm run lint`                                                                                                                                     | **0 errors**, 1 pre-existing warning (`postcss.config.mjs`, untouched file)                                                                   |
| 5   | Prettier (node API, config-resolved) on all 6 changed source/test files + this report                                                              | Clean                                                                                                                                         |
| 6   | `npm run build`                                                                                                                                    | **Pass** — 37/37 routes generated                                                                                                             |
| 7   | `git diff --check` on changed files                                                                                                                | No whitespace errors (only local CRLF notices)                                                                                                |
| 8   | Browser render smoke (via dev server on :3000)                                                                                                     | Not re-run this session; previous session evidence stands (renders, anonymous `/dashboard` → login)                                           |
| 9   | Backend suite (`pytest`, rebuilt venv)                                                                                                             | **1,864 passed / 101 skipped / 0 failed** (unchanged; skips = PostgreSQL/Redis environment-only). No backend change was made                  |

**No test was deleted, weakened, or suppressed** to make these results green. The two new lint-rule violations that appeared mid-fix were resolved by restructuring (render-time state adjustment, event-handler-scoped `setLoadingMore`), never by disabling rules.

## I. Corrected test-count arithmetic (reconciling the earlier report)

- Baseline at `f3c3172` (Batch 3 start): **210 tests / 31 files** — 199 before the proxy route-guard fix, +11 `proxy.test.ts` guard tests (the guard fix, all CI-verified).
- Batch 3 added exactly **15**: 11 conversations service (`conversations.test.ts`) + 2 panel smoke (`lead-conversations-panel.test.tsx`) + 2 assignment-history (added into `teams-users-assignment.test.ts`).
- Batch 3 total: **225 / 33 files**, 0 failed.
- The earlier report's "199 pre-existing + 26 added" double-counted the 11 guard-fix tests. Corrected in F.1 there and in its new Errata section.
- Review remediation added **8** (`principal-cache.test.ts`): **233 / 34 files**.

## J. Remaining limitations (not remediated, by design or by environment)

1. Component-level interactive coverage cannot run in this repo's node-only test environment (no jsdom/testing-library); panel rendering is smoke-tested only, interaction logic is covered by service-level tests + code guards. Not claimed as tested.
2. Two-organization live rehearsal, RLS/integration tests (PostgreSQL), and Redis-dependent tests are unavailable in this environment — unchanged; they must pass in CI/staging before merge.
3. PDF (Sheet 2B #14–#20) fidelity and the 360–1440 px viewport matrix remain unverified — no programmatic window resize exists in the in-app browser; no false claims are made.
4. `git diff --check` prints local CRLF notices for some files (cosmetic, Windows `core.autocrlf`); CI checkout is LF.
5. Message pagination hard cap of 1,000 with no cursor remains a backend contract fact, now disclosed in the UI, not fixable here.
6. npm audit status (12 findings incl. zod 3 HIGH) unchanged and out of scope; still requires founder disposition.

## K. Protected state

- `database/migrations/0016_search_trigram_indexes.sql`: untracked-protection intact, `M` with identical baseline diff (1+/46−), never read/restored/staged.
- All pre-existing untracked files (and the earlier-untracked `frontend/src/proxy.test.ts`, already tracked) preserved.
- Nothing staged, committed, pushed, merged, amended, or rebased; branch remains `feat/phase6-commercial-v1` @ `f3c3172`, **remote unchanged**. `main` never checked out. PR #2 remains Draft. Batch 4+ untouched.

## L. Final verdict

# **CONDITIONAL PASS — Implementation Complete; Environment-Gated Verification Remains**

**What this remediation demonstrably fixed (evidence in H):** truthful record-only conversation copy; distinct loading/error/empty states with retry everywhere a request can fail; no false "empty" success after failure; previous pages preserved on refresh failure; stale-response generation guards and remount keys covering lead/principal switches; composite-identity React Query cache isolation with 8 new passing tests; visible pagination disclosure with working "Load more" for assignment history; corrected test-count arithmetic in the prior report.

**Why not PASS:** the environment could not run (a) full interactive DOM coverage (node-only test env), (b) PostgreSQL/Redis-backed backend integration tests (101 skips), or (c) the PDF-fidelity and viewport matrix. These gates exist and are recorded; the frontend gates that can run here are all green.

**Remaining founder actions:** merge only after CI verifies the exact commit on a runner with PostgreSQL/Redis (including RLS tenant-isolation suites), supply D-09 (design source) and a resizable visible browser window for the visual QA pass, and decide the legitimate-followup contract cleanup (optional relaxing of legacy required fields) with a matching OpenAPI regeneration — none of which is authorized in this remediation.
