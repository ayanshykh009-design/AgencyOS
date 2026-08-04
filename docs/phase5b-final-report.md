# Phase 5B — Release Audit Certification Report

**Date:** 2026-08-04
**Audit type:** Independent release audit (baseline `0b2b9c1`, Phase 5A complete)
**Auditor:** AgencyOS engineering (AI-assisted review)
**Scope:** All Phase 5B work (B1–B7) — envelope encryption + key rotation, the
builtin execution engine, event fan-out guards, CSP hardening, dashboard/search
performance, the invite acceptance page, and the schedule dispatcher.
**Gate:** **🟢 RELEASE CERTIFIED**

> This report supersedes `docs/phase5b-final-report.md` (the pre-audit gate
> report). It reflects an independent re-review of the actual codebase at
> `0b2b9c1` + Phase 5B work, the defects found and fixed during that review, and
> a fresh run of every gate.

---

## 1. Inventory vs Baseline (`0b2b9c1`)

A full `git status` / `git diff --stat 0b2b9c1` review was performed. Every
change is Phase 5B-scoped; no unintended edits to Phase 1–5A modules were found.

| Layer | Files touched |
| ----- | ------------- |
| Backend core | `core/{config,crypto,middleware}.py` + new `core/{csp,kms,metrics}.py` |
| Backend models | `models/{credential,workflow_trigger}.py` |
| Backend repos | `repositories/{credential,workflow_trigger}.py` + new `repositories/dashboard.py` |
| Backend services | `services/{credential_service,dashboard_service,execution_adapter,workflow_event_service,workflow_service,workflow_trigger_service}.py` + new `services/{builtin_execution,schedule_cron,schedule_dispatcher}.py` |
| Backend workers | `workers/execution_worker.py` + new `workers/credential_worker.py` |
| Backend endpoints | `api/v1/endpoints/credentials.py` |
| Backend schemas | `schemas/{credential,workflow_trigger}.py` |
| DB | `database/migrations/0014/0015/0016`, `database/schema/{workflows,leads,tasks}.sql`, `database/supabase/policies/credential_key_versions.sql` (new) |
| Frontend | `app/(dashboard)/credentials/page.tsx`, `services/credentials.ts`, `types/index.ts`, new `app/invite/` route |
| Tests | 17 new/modified backend unit files, 2 integration files, 2 frontend test files |
| Docs | `docs/{database,observability,security}.md`, `docs/phase4.5-production-checklist.md`, `docs/api/endpoints/*` |

Out-of-scope defects discovered (pre-existing, fixed — see §11): Next.js 16
async-`params` handling in two Phase 5A dashboard pages.

## 2. B1 — Envelope Encryption / KMS / Credential Stack

**Source reviewed:** `core/{crypto,kms,config}.py`, `models/credential.py`,
`repositories/credential.py`, `services/credential_service.py`,
`workers/credential_worker.py`, `api/v1/endpoints/credentials.py`,
`0015_credential_key_versions.sql`, `supabase/policies/{credentials,credential_key_versions}.sql`,
tests `test_{kms,credential_service,credential_worker}.py`.

**Findings — all PASS:**

- Envelope format `v<version>:<base64(nonce || ct)>`; HKDF-SHA256 key derivation
  with fixed salt/info; AES-256-GCM with random 96-bit nonces.
- Legacy rows (pre-versioning plaintext or `base64(nonce||ct)` without prefix)
  are detected and handled transparently; `key_version='0'` is the reliable
  legacy sentinel because `CREDENTIAL_KEY_VERSION` is validated as a positive
  integer at boot.
- Dual-read during rotation: `CREDENTIALS_ENC_KEY_PREVIOUS` is only accepted for
  `version = CREDENTIAL_KEY_VERSION - 1`; versioned blobs that fail
  authentication raise (corruption is never silently accepted).
- `kms.py`: `KmsProvider` ABC + `EnvKeyProvider`, cached `get_kms_provider()`.
- `config.py`: new settings validated at boot (`_validate_enc_key` in both
  `validate_runtime()` and `validate_for_production()`); `CREDENTIALS_ENC_KEY`
  is mandatory in production.
- Model ↔ migration parity: `key_version text NOT NULL DEFAULT '0'` and
  `last_rotated_at timestamptz` are mirrored in both the ORM model and migration
  `0015` (additive, idempotent).
- Service layer: create encrypts under the current key; update never touches the
  stored secret; rotate re-encrypts and bumps version; `get_secret` is
  adaptor-only (never exposed via an endpoint).
- Worker: `rekey_tick()` is restart-safe/idempotent, decrypts with
  `key_version=credential.key_version`, re-encrypts under the current key, and
  retires the previous version only when `stale == 0`. Rows that fail decryption
  are logged and skipped (never re-encrypted into garbage).
- Endpoint: every route (incl. `POST /{id}/rotate`) requires
  `Permission.CREDENTIAL_MANAGE`; responses expose only masked previews.
- RLS: `credentials` and `credential_key_versions` are RLS-enabled with no
  policies (service-role manages them) — the RLS-only policy files are present.

**Defect found & resolved (§11 F4):** pre-versioning plaintext that literally
starts with `v<digits>:` is indistinguishable from an unknown-key envelope. The
existing, deliberately-tested contract (`test_unsupported_key_version_raises`)
raises loudly rather than silently returning ciphertext as a secret. This is
accepted by design and documented here; no code change.

## 3. B2 — Builtin Execution Engine + Fail-Fast Validation

**Source reviewed:** `services/{builtin_execution,execution_adapter,workflow_service}.py`,
`workers/execution_worker.py`, `test_builtin_execution.py`, `test_execution_adapter.py`.

**Findings — all PASS:**

- `builtin_execution.py` is stdlib-only and declarative: JSON-only step
  definitions, whitelisted ops (`set`/`copy`/`condition`/`error_if`), dotted-path
  access restricted to `[A-Za-z0-9_]`, `{{ path }}`/`{{ path ?? default }}`
  templates. No `eval`/`exec` anywhere.
- Resource bounds are enforced via settings (`BUILTIN_MAX_STEPS`,
  `BUILTIN_MAX_CONDITION_DEPTH`, `BUILTIN_MAX_TEMPLATE_LENGTH`,
  `BUILTIN_MAX_RESULT_SIZE_BYTES`) and validated at boot.
- `execution_adapter.py`: `ExecutionAdapter` ABC; `N8nAdapter` (webhook,
  `/webhook/workflow-{id}`) and `BuiltinAdapter`; `get_adapter()` dispatch.
- `workflow_service.py` diff vs baseline is surgical: `_validate_builtin` runs
  on **both** create and update paths and fails fast with
  `workflow.builtin_definition_invalid` (400); invalid definitions can never be
  persisted.
- `execution_worker.py` phases reviewed (retry requeue → queue drain → stale
  timeout → schedule tick); schedule phase is isolated and never blocks the
  queue; cadence-gated in `run_loop`.

## 4. B3 — Trigger Repository + Event Fan-Out Guards

**Source reviewed:** `repositories/workflow_trigger.py`,
`services/workflow_event_service.py`, `services/schedule_cron.py`,
`services/schedule_dispatcher.py`, `0014_schedule_last_fired.sql`,
`test_workflow_event_service.py`, `test_schedule_dispatcher.py`.

**Findings — all PASS (one hardening applied, §11 F6):**

- `reserve_last_fired()` is an optimistic atomic claim (`last_fired_at IS NULL
  OR last_fired_at < previous_fire`) — exactly one worker wins per tick; the
  partial index `idx_workflow_triggers_schedule_due` serves the sweep query.
- `workflow_event_service.publish()`: organization check → payload size cap
  (fail-fast 400 `event.payload_too_large` **before any write**) → insert event →
  fetch matching triggers with `limit = max_fanout + 1` → truncation detected by
  the +1 → bounded queueing in the same transaction → commit with retry.
  `trigger.enabled` is re-checked per trigger; per-trigger queue failures are
  swallowed and counted so one bad workflow never aborts the fan-out.
- `previous_fire`/`validate_cron` in `schedule_cron.py` handle never-firing and
  invalid crons (counted + logged, never raised).
- Trigger create/update validates `schedule_cron` fail-fast
  (`trigger.schedule_cron_invalid`, 400).

## 5. B4 — Invite Page / Teams / Proxy / Permissions

**Source reviewed:** `frontend/src/app/invite/[token]/page.tsx`,
`frontend/src/services/teams.ts`, `frontend/src/proxy.ts`,
`frontend/src/lib/api-client.ts`, `backend/app/api/v1/endpoints/teams.py`,
`backend/app/services/team_service.py`, `backend/app/schemas/team.py`.

**Findings — all PASS (one critical bug found & fixed, §11 F1):**

- Backend contract matches the frontend exactly: `GET /teams/public/{token}`
  (unauthenticated, rate-limited) returns `{ email, full_name, role,
  organization_name }`; `POST /teams/accept` takes `{ token, full_name,
  password }`. `TeamService.invite_url()` emits `{FRONTEND_URL}/invite/{token}`.
- `frontend/src/proxy.ts` matcher is `["/(dashboard)/:path*", "/login/:path*"]` —
  the invite route is intentionally public and stays out of the auth proxy.
- Error mapping in `inviteError()` matches the codes `api-client.ts` produces
  (`team.invite_expired`, `team.invite_invalid`, `team.user_exists`,
  `network.error`, `request.failed`).
- All routes require the appropriate permission via `require_permission`; the
  invite flow is the only public account-creation path and is rate-limited.
- `teams.py` intentionally omits `from __future__ import annotations` (slowapi
  limiter) — not a defect, do not "fix".

## 6. B5 — CSP Default-On + Validated Builder

**Source reviewed:** `core/csp.py`, `core/middleware.py`, `core/config.py`,
`frontend/next.config.mjs`, `docs/{security.md,phase4.5-production-checklist.md}`,
`test_csp.py`, `test_health.py`.

**Findings — all PASS:**

- `build_csp_policy()` emits `default-src 'self'; base-uri 'self';
  frame-ancestors 'self'; form-action 'self'; object-src 'none'; frame-src
  'none'`, widens `connect-src` only from `CSP_CONNECT_ORIGINS`, and adds
  `upgrade-insecure-requests` in production.
- `CSP_CONNECT_ORIGINS` is validated at boot (`validate_csp_origins`); malformed
  origins (bad scheme, wildcards/quotes, invalid ports) fail fast.
- `ENABLE_CSP` defaults to `true`; production boot refuses a disabled CSP.
- `middleware.py` diff vs baseline is surgical: it delegates to
  `build_csp_policy()` instead of the old hardcoded string; the rest of the
  security-header middleware (Referrer-Policy, Permissions-Policy, request-ID) is
  unchanged.
- Note: the frontend (Next.js) sends no CSP header itself — the API gateway
  middleware does. Documented; acceptable because the SPA is served behind the
  gateway.

## 7. B6 — Dashboard Single-CTE + Search Trigram Indexes

**Source reviewed:** `repositories/dashboard.py`, `services/dashboard_service.py`,
`api/v1/endpoints/dashboard.py`, `schemas/dashboard.py`,
`0016_search_trigram_indexes.sql`, `test_dashboard_repository.py`.

**Findings — all PASS (one consistency fix, §11 F7):**

- `DashboardRepository.summary_snapshot()` folds all ~14 counters across 8 tables
  (plus the recent-activity feed collapsed into a JSON array) into **one** SQL
  statement of single-row CTEs, so the request is a single round trip. Every CTE
  predicate mirrors the individual repository method it replaces (lead funnel
  with `deleted_at IS NULL`, task open/overdue/due-today/completed-30d windows,
  provider_usage spend window, conversation/outreach/import counts, and the
  `ORDER BY occurred_at DESC, id DESC LIMIT 10` activity feed).
- All values are parameterized (`:org_id`, `:now`, `:start_of_day`,
  `:end_of_day`, `:since_30d`) — no SQL injection surface.
- The final `SELECT` is a `CROSS JOIN` of single-row CTEs, so exactly one row is
  returned even when tables are empty.
- `dashboard_service.py` is now a thin shaper; response contract unchanged.
- `0016_search_trigram_indexes.sql`: `pg_trgm` + 7 GIN indexes (5 × leads, 2 ×
  tasks) for the leading-wildcard `ILIKE '%q%'` searches; idempotent.

## 8. Database Consistency

Model ↔ migration ↔ canonical schema ↔ Supabase policy parity was swept:

- `WorkflowTrigger.last_fired_at` (model) == `0014` == `schema/workflows.sql`. ✅
- `Credential.{key_version,last_rotated_at}` + `credential_key_versions` model ==
  `0015` == `schema/workflows.sql` (incl. trigger + RLS). ✅
- `0016` trigram indexes: **were missing from the canonical `schema/leads.sql`
  and `schema/tasks.sql`** (0014/0015 were mirrored; 0016 was not). Fixed — the
  indexes are now in both the migration and the canonical schema. ✅
- Supabase policy files exist for every table incl. the new
  `credential_key_versions.sql` (RLS-only; service-role manages). ✅
- Migration discipline: all three migrations are additive, idempotent
  (`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`), fill legacy rows with a fast
  `DEFAULT`, and are zero-data-loss. No columns dropped, no data rewritten. ✅

## 9. Code-Quality Scan

- TODO/FIXME/HACK scan of every Phase 5B file: no real markers (matches are
  `TaskStatus.TODO` enum references and pre-existing TODOs in `core/database.py`,
  `core/config.py`, `frontend/src/app/error.tsx`).
- No dead code, no duplicated logic, no new runtime dependencies introduced
  anywhere in the batch.
- Structure discipline held: thin endpoints → service → repository → model, and
  `config.py` owns all settings with boot-time validation.

## 10. Gates Re-Run (post-fix, from a clean state)

| Gate | Result | Detail |
| ---- | ------ | ------ |
| Backend lint | ✅ | `ruff check app tests` — all checks passed |
| Backend types | ✅ | `mypy app` — no issues in 192 source files |
| Backend tests | ✅ | **637 passed / 25 skipped** (662 collected; skips = integration needing a live DB — run in CI with the Postgres service). Includes 2 new dispatcher tests (see §11 F6) |
| Frontend lint | ✅ | `eslint .` — 0 errors (1 pre-existing warning in `postcss.config.mjs`) |
| Frontend types | ✅ | `tsc --noEmit` — clean |
| Frontend format | ✅ | `prettier --check .` — all files compliant |
| Frontend tests | ✅ | 17 files / 96 tests passed |
| Frontend build | ✅ | `next build` — production build; `/invite/[token]`, `/leads/[id]`, `/workflows/[id]` are dynamic (`ƒ`) routes |

## 11. Defects Found & Resolved During This Audit

| ID | Finding | Severity | Resolution |
| -- | ------- | -------- | ---------- |
| F1 | `invite/[token]/page.tsx` accessed `params.token` synchronously — Next.js 16 made page `params` a `Promise`, so the route would fail at runtime (and this exact route is the new Phase 5B deliverable). | **Critical** | Converted to `const { token } = use(params)` with `params: Promise<{ token: string }>`; validated by `tsc` + `next build` |
| F2 | Pre-existing: `(dashboard)/workflows/[id]/page.tsx` (line 58) same sync-`params` defect. | High | Fixed with `use(params)`; flagged as pre-existing Phase 5A breakage |
| F3 | Pre-existing: `(dashboard)/leads/[id]/page.tsx` (line 38) same defect. | High | Fixed with `use(params)`; flagged as pre-existing Phase 5A breakage |
| F4 | `crypto.decrypt_secret` can't distinguish a pre-versioning plaintext that starts with `v<N>:` from an unknown-key envelope. | Low | Accepted by design — unknown key versions fail loudly (tested) to avoid silently returning ciphertext; documented in §2 |
| F5 | `0015` enabled RLS on `credential_key_versions` but no canonical Supabase policy file existed. | Low | Added `database/supabase/policies/credential_key_versions.sql` (RLS-only, mirroring `credentials.sql`) |
| F6 | `ScheduleDispatcher` called `session.rollback()` on a mid-batch queue failure, discarding earlier successful dispatches in the same batch (deferred delivery, wasted transaction). | Medium | Per-trigger **savepoint** isolation via `session.begin_nested()`; added `test_partial_batch_failure_preserves_earlier_queue`; updated the rollback-semantics test |
| F7 | `0016` trigram indexes not mirrored into the canonical schema (`leads.sql`, `tasks.sql`). | Low | Added the 7 GIN indexes to the canonical schema files |

## 12. Risk Register (residual)

| Risk | Level | Owner | Status |
| ---- | ----- | ----- | ------ |
| 25 DB-backed integration tests not run locally | Low | eng | Run in CI with the Postgres service; SQL mirrors are kept in sync (§8) |
| `pg_trgm` GIN indexes add write amplification | Low | eng | Bounded (7 columns); search is the targeted hot path |
| CSP `connect-src` may need widening as UI origins grow | Low | product | One-line `CSP_CONNECT_ORIGINS` addition, validated at boot |
| Builtin engine complexity ceiling (50 steps / depth 3) | Low | product | Documented limits; n8n adapter remains the escape hatch |

## 13. Production Deployment Notes

1. Set `CREDENTIALS_ENC_KEY` (+ `CREDENTIAL_KEY_VERSION`) in the secret manager
   **before** deploying; pre-versioning plaintext/legacy rows read fine until
   the opt-in rekey worker (`CREDENTIAL_REKEY_ENABLED=true`) upgrades them.
2. Keep `ENABLE_CSP=true` (the default). Add browser-reachable origins to
   `CSP_CONNECT_ORIGINS`; production boot refuses a disabled CSP.
3. No frontend config change is required for the invite route — it resolves via
   `FRONTEND_URL`.
4. Deploy the three additive migrations (0014 → 0015 → 0016) in order; each is
   safe to re-run.

---

## Release Audit Certification — 🟢

**Verdict: PASS — CERTIFIED FOR PRODUCTION RELEASE**

- All seven Phase 5B items (B1–B7) verified against the actual codebase at
  baseline `0b2b9c1`; no unimplemented backlog items.
- 7 audit findings addressed: 1 critical runtime bug and 2 pre-existing
  equivalent defects fixed (F1–F3), 1 correctness hardening applied (F6), 3
  consistency gaps closed (F5, F7) or documented as by-design (F4).
- Every production gate re-run post-fix and green: backend 637 passed / 25
  CI-only skips, `ruff` and `mypy` clean; frontend 96 tests, `eslint` 0 errors,
  `tsc` clean, `prettier` clean, `next build` succeeds with all dynamic routes
  compiling.
- No new runtime dependencies; migrations are additive and idempotent; the
  CI pipeline required no changes.
- **This batch is approved to ship.**
