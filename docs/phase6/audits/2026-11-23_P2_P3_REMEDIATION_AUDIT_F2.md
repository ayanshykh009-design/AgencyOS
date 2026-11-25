# P2/P3 Remediation Audit — F2 (independent reviewer)

**Date:** 2026-11-23
**Repository:** `D:\AgencyOS`
**Branch / HEAD:** `feat/phase6-commercial-v1` @ `244e6074fa1e016a7318ab0e011927c93aa178c7` (matches supplied baseline)
**Artifact:** second consecutive independent audit (F2)

## Scope

Only the P2-1 … P3-6 remediation and directly affected code/tests/docs. No other audit artifact (including F1) was read or relied upon. Static inspection of source/tests/docs plus safe Git inventories only.

**Prohibited actions avoided:** no staging/commit/push/merge/PR/deploy/release/branch-switch/reset/clean/stash/rebase/checkout/restore; no Batch 7 work; no full pytest, migration-backed tests/fixtures, `test_pg_helpers.py`, integration/E2E, Alembic upgrade/replay, live PostgreSQL/RLS/Redis, browser E2E, live providers, or production validation. No repository file was modified except this artifact.

**Protected-path discipline:** `database/migrations/0016_search_trigram_indexes.sql` was never opened, read, printed, searched, diffed, hashed, staged, modified, renamed, or deleted. Every broad Git status/diff/log inventory carried the exclusion pathspec `:!database/migrations/0016_search_trigram_indexes.sql`.

## Exact files inspected

- P2-1: `backend/app/llm/error_sanitizer.py`, `backend/tests/unit/test_ai_hardening.py`; usage grep across `backend/app` (`tools/n8n_tool.py`, `services/ai_service.py`, `ai/brain.py`, `services/founder_chat_service.py`).
- P2-2/P2-3: `docs/AGENCYOS_BATCH5_BATCH6_FINAL_CLOSURE_REPORT.md`.
- P3-1: `backend/app/services/workflow_event_service.py`, `backend/tests/unit/test_workflow_event_service.py`.
- P3-2: `backend/app/services/founder_action_service.py`, `backend/tests/unit/test_founder_approval_atomicity.py`, `backend/app/repositories/founder_action_proposal.py` (`finish_execution` contract).
- P3-3: `frontend/src/app/(dashboard)/batch5-defect-regressions.test.ts`, `frontend/src/types/index.ts`, `frontend/src/types/intelligence.ts`, `backend/app/models/enums.py`, `frontend/src/app/(dashboard)/founder/proposals/page.tsx`, `frontend/src/app/(dashboard)/founder/intelligence/page.tsx`.
- P3-4: `docs/AGENCYOS_DEPENDENCY_RISK_ACCEPTANCE.md`.
- P3-5: `frontend/src/lib/validation/auth.ts`, `frontend/src/lib/validation/marketing.ts`, `frontend/src/lib/validation/auth.test.ts`, `frontend/src/lib/validation/marketing.test.ts`, `frontend/package.json`, plus `.email(` grep over `frontend/src`.
- P3-6: `.github/workflows/ci.yml`.

## Commands used (Git inventories — all include protected-path exclusion)

1. `git status --porcelain=v1 --untracked-files=all -- :!database/migrations/0016_search_trigram_indexes.sql`
2. `git branch --show-current && git rev-parse HEAD && git status --porcelain=v1 --untracked-files=no -- :!database/migrations/0016_search_trigram_indexes.sql`
3. `git diff HEAD -- .github/workflows/ci.yml -- :!database/migrations/0016_search_trigram_indexes.sql`
4. `git diff --cached --name-only -- :!database/migrations/0016_search_trigram_indexes.sql && git log --oneline -5 -- :!database/migrations/0016_search_trigram_indexes.sql`

Non-Git inspections used the file read/grep tools on the explicit paths listed above; no repository-wide recursive grep/search was run.

## Verification evidence

- **P2-1:** `safe_error()` logs only `log_label`, `request_id_var.get()`, and `type(detail).__name__`; the raw `detail` text is never interpolated into the log record or return value. `test_ai_hardening.py` asserts host/body/secret strings absent from `caplog.text` for both exception and string details (and `type=str` logged). All 5 production call sites use `safe_error`. The file contains 15 test definitions, matching the reported 15 passed.
- **P2-2/P2-3:** A6/B3 are explicitly retracted/unsubstantiated (lines 26, 285, 287, 448); `PUSH BLOCKED` stated explicitly (line 449); the only declared final status is exactly `READY FOR LOCAL COMMIT REVIEW ONLY — PUSH BLOCKED` (line 453). `READY WITH DOCUMENTED CARRYOVERS` is scoped to Batch 7 readiness, not final status.
- **P3-1:** `_serialized_size()` counts UTF-8 bytes (`json.dumps(..., ensure_ascii=False).encode("utf-8")`). The complete queued input `{"event": payload, "trigger_config": trigger.config}` is capped for every enabled trigger at lines 123–132, before `event_repo.add`/`flush` (lines 156–158) or `queue` (line 165). Regressions assert `event.input_too_large`, no event write, no queue call, and multibyte (`é`) accounting. 17 test definitions match the reported 17 passed.
- **P3-2:** `_settle_execution()` checks `finish_execution()`'s boolean; on `False` it rolls back and raises `founder_proposal.not_pending` (409) without applying a terminal transition or returning a state it does not own; both success and failure paths route through it. `finish_execution()` is typed `-> bool` and returns `result.scalar_one_or_none() is not None`. Regressions `test_lost_success_settlement_fails_closed` / `test_lost_failure_settlement_fails_closed` assert rollback, 409, and status remaining `EXECUTING`. 13 test definitions match the reported 13 passed.
- **P3-3:** The regression derives `FounderProposalStatus` (8 values) and `IntelligenceSignalStatus` (4 values) from the exported TS unions and compares sorted arrays with `.toEqual` against the full filter arrays, not a sample. The TS unions match `backend/app/models/enums.py` exactly, and the page arrays contain all 8 / 4 values plus `"all"`.
- **P3-4:** Line 9 states `frontend/package-lock.json` is "uncommitted local", "not part of the committed baseline", and "must be staged explicitly if accepted" — not committed.
- **P3-5:** Both schemas use `z.string()... .check(z.email({ error: EMAIL_MESSAGE }))`; grep over `frontend/src` found no deprecated string `.email(message)` call (only the two `z.email` calls and the static test's negative assertions). `zod` is pinned `^4.6.7`; tests assert field-level email messages and the static guard asserts the API shape in both files.
- **P3-6:** Diff against HEAD shows the `-    # placeholder` line removed; the only remaining "placeholder" occurrence is the legitimate `.env.example` comment. Trigger block (`push: [main]`, `pull_request: {}`) is untouched. Gate changes are tightenings only (`npm install`→`npm ci` + lockfile diff check, added OpenAPI drift check, `npm audit` critical→moderate); nothing weakens security, suppresses tests, or makes push look safe, and push remains classified `PUSH BLOCKED`.
- **State/regressions:** `git diff --cached --name-only` empty → staging area empty. HEAD equals the supplied baseline → no new commit; last 5 commits are unchanged history, tip `244e607` "finalize batch 5 and batch 6 integration". No Batch 7 code/route/asset/migration in status. Pre-existing untracked files are preserved. Remote PR/push/deploy state is not locally verifiable; no local evidence of such activity and the docs explicitly deny it. No in-scope regression found; the closure report's differing pre-remediation counts are explained by its supersession note (line 11), and the intentionally post-audit remediation final report's absence is not treated as a finding.

No tests were rerun in this audit (per instruction); implementer-provided gate results were treated as claims and cross-checked only for internal consistency with test file counts and source shape.

## Final verdict

No actionable in-scope P0/P1/P2/P3 findings.

ZERO FINDINGS
