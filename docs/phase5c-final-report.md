# Phase 5C — Automation Foundation Hardening: Release Audit Certification Report

**Date:** 2026-08-07
**Audit type:** Implementation + release audit of the Phase 5C scope (`docs/phase5c-plan.md`, status: approved)
**Baseline:** `0b2b9c1` (Phase 5B complete) → uncommitted working tree (this batch)
**Auditor:** AgencyOS engineering (AI-assisted review)
**Scope:** All Phase 5C items 1–8 — workflow reliability, queue hardening, execution
observability, automation monitoring, operational controls (kill switch), audit &
retention, performance hardening, and documentation.
**Gate:** **🟢 RELEASE CERTIFIED**

> The kill switch is now genuinely wired end-to-end (the prior audit found it was
> defined but inert). This report covers that fix plus the full hardening batch,
> and reflects a fresh run of every gate after all changes.

---

## 1. Inventory vs Baseline

A full `git status` / `git diff --stat` review was performed. The batch is 62
tracked files changed (~14.3k insertions / 263 deletions) plus ~45 new files.
Every change is Phase 5C-scoped; no unintended edits to unrelated modules.

| Layer | Files (new †) |
| ----- | -------------- |
| Endpoints | `api/v1/endpoints/workflow_executions.py` + `automation_control.py`†, `monitoring.py`† |
| Models | `models/{workflow_execution,user}.py`, `models/enums.py` + `execution_event.py`†, `worker_health.py`†, `system_setting.py`† |
| Repos | `repositories/{workflow_execution,workflow,workflow_event,activity_log}.py` + `execution_event.py`†, `worker_health.py`†, `system_settings.py`† |
| Schemas | `schemas/workflow_execution.py` + `execution_event.py`†, `worker_health.py`†, `system_settings.py`†, `monitoring.py`† |
| Services | `workflow_execution_service.py`, `execution_adapter.py`, `n8n_client.py`, `workflow_event_service.py`, `schedule_dispatcher.py`, `builtin_execution.py` + `execution_event_service.py`†, `automation_control_service.py`†, `monitoring_service.py`†, `operational_monitoring_service.py`† |
| Workers | `execution_worker.py` + `retention_worker.py`† |
| Core | `config.py`, `metrics.py`, `observability.py`, `permissions.py` (`AUTOMATION_CONTROL` admin-only), `api/v1/api.py` |
| DB | `migrations/0017_automation_hardening.sql`†, `migrations/enums/11_automation_hardening.sql`†, `schema/workflows.sql`, `schema/00_enums.sql`, `schema/{execution_events,worker_health,system_settings}.sql`†, `supabase/policies/{execution_events,worker_health,system_settings}.sql`† |
| Frontend | `services/monitoring.ts`† + `types/monitoring.ts`†, `lib/permissions.ts`, `app/(dashboard)/{operational-monitoring,worker-monitoring}/`†, `components/{auth/permission-guard.tsx,monitoring/}`†, `app/(dashboard)/executions/`, `components/ui/*`, `types/index.ts`, `lib/constants.ts` |
| Tests | `tests/unit/{test_automation_control_service,test_execution_event_service,test_hardening_repositories,test_monitoring_service,test_retention_worker}.py`† + edits to `test_execution_worker`, `test_schedule_dispatcher`, `test_workflow_event_service`, `test_workflow_execution_service`, `test_n8n_client`, `test_builtin_execution`, `test_execution_adapter`, `test_metrics`, `test_enums`, `test_models`, `tests/api/test_automation_api.py`, `tests/integration/test_database_schema.py` |
| Docs | `docs/operations/{admin-guide,troubleshooting-automation}.md`†, `docs/api/endpoints/{automation-control,monitoring}.md`†, `docs/{architecture,database,observability,security,README}.md`, `docs/api/endpoints/{README,workflow-executions,workflow-events,workflows}.md`, `docs/api/openapi.yaml`, `docs/phase5c-plan.md`†, `database/migrations/README.md` |

---

## 2. Reliability (plan §1)

**Source:** `workflow_execution_service.py`, `execution_worker.py`, `n8n_client.py`,
`workflow_execution.py`, `0017_automation_hardening.sql`.

**Findings — all PASS.**

- **TOCTOU closed.** `timeout()` now transitions only from `status='running'`
  (`WHERE … AND status='running'`); `cancel` uses guarded optimistic transitions.
  Exactly one caller wins each state move.
- **In-flight cancel.** `cancel_requested_at` (+ `cancelled_by_user_id`) added to
  the model and migration; cancel flags a running execution and the worker honors
  the flag (skips starting a flagged `queued`; lands `running` on `cancelled`
  when the adapter returns with the flag set).
- **Hard per-execution timeout.** `process_queued` wraps `adapter.execute` in
  `asyncio.wait_for(EXECUTION_TIMEOUT_SECONDS)` (default 300); a hang is marked
  `timed_out` directly (terminal, no auto-retry) and records a `timeout_guard`
  timeline event. A hung adapter can no longer wedge a worker task between sweeps.
- **Status-leap guards.** `complete()`/`fail()` are valid only from `running`; if
  `cancel_requested_at` is set when the adapter returns, the execution lands on
  `cancelled`, not `succeeded`.
- **n8n diagnostics.** `n8n_client.py` captures non-2xx response bodies (bounded +
  sanitized) into error metadata. `complete`/`fail` payload bodies are capped at
  `BUILTIN_MAX_RESULT_SIZE_BYTES` → `413 execution.payload_too_large` via the
  unified envelope.

## 3. Queue hardening (plan §2)

**Findings — all PASS.**

- **Idempotency.** `idempotency_key` (nullable) + partial unique index
  `(organization_id, idempotency_key) WHERE idempotency_key IS NOT NULL`;
  `queue()` rejects a duplicate key with `409 execution.duplicate_idempotency_key`.
- **Per-org pending cap** `EXECUTION_MAX_PENDING_PER_ORG` (default 500) → `409
  execution.pending_cap_exceeded`; callers holding `EXECUTION_MANAGE` bypass.
- **Fair drain.** `process_queued` selects candidate orgs via
  `get_queued_orgs(EXECUTION_ORGS_PER_SWEEP)` (GROUP BY org, oldest-first) then
  drains per-org batches within `EXECUTION_BATCH_SIZE` — one busy org cannot starve
  the rest.
- **N+1 killed.** Workflows are batch-fetched once per org via
  `workflow_repo.get_many(...)`.
- **Statement timeout.** Every sweep phase sets `SET LOCAL statement_timeout`
  from `EXECUTION_STATEMENT_TIMEOUT_SECONDS` (default 30) so a runaway query never
  pins a DB connection.
- **Counters** `execution_queued/drained/retried/failed/timed_out/cancelled_total`
  + per-phase duration histogram (`execution_worker_phase_seconds`).
- **At-least-once drain** documented in `workflow-executions.md`.

## 4. Execution observability (plan §3)

**Source:** `execution_event_service.py`, `execution_event.py`, `0017`,
`schema/execution_events.sql`, `/workflow-executions/{id}/events`.

**Findings — all PASS.**

- **`execution_events`** is an append-only per-attempt technical timeline
  (13-value `execution_event_type` enum incl. `timeout_guard`; `metadata` JSONB
  holds duration/step/error/actor/adapter). Indexes `(execution_id, occurred_at)`
  and `(organization_id, workflow_id, occurred_at)`.
- **Best-effort writes:** a timeline failure never fails the execution. Duration
  is derived and exposed on `WorkflowExecutionRead`.
- **Timeline API** `GET /workflow-executions/{id}/events` (`EXECUTION_READ`,
  pageable) is live and documented.
- **Completed audit trail:** `activity_logs` receives
  `execution_queued/started/completed/failed/retried/cancelled` plus
  `automation_paused/resumed` with actor and before/after status in `metadata`
  (verified in `automation_control_service.pause/resume` and the service
  transitions).

## 5. Automation monitoring (plan §4)

**Source:** `worker_health.py`, `monitoring_service.py`,
`operational_monitoring_service.py`, `monitoring.py`, frontend monitoring pages.

**Findings — all PASS.**

- **`worker_health`** heartbeat row upserted per loop iteration + on shutdown;
  `loop_ok`/`last_error`/counters; `stale` when older than
  `EXECUTION_POLL_INTERVAL_SECONDS × 3`.
- **Endpoints under `/monitoring/`** (a deliberate naming choice vs the plan's
  `/automation/stats` — all documented in `docs/api/endpoints/monitoring.md`):
  `operational/summary`, `execution-statistics`, `worker-statistics`,
  `schedule-statistics`, `retention-statistics`, `automation-lifecycle`,
  `heartbeat-visibility`, `execution-timeline`, `execution-history`,
  `queue-status`, `monitoring-information`. Authz: `AUTOMATION_READ` (cross-org
  reads are operator-only), `operational/summary` additionally
  `AUTOMATION_MANAGE`.
- **Frontend:** `executions`, `operational-monitoring`, and `worker-monitoring`
  pages added under `(dashboard)/`; `services/monitoring.ts` + `types/monitoring.ts`;
  the frontend permission map now includes `execution_read/write/manage`
  (`execution_manage` → `_ADMIN_ONLY`).

## 6. Operational controls — kill switch (plan §5)

**Source:** `automation_control_service.py`, `system_setting.py`,
`system_settings.py` repo, `automation_control.py` endpoint, and the gates in
`workflow_execution_service.py`, `schedule_dispatcher.py`, `workflow_event_service.py`,
`execution_worker.py`.

**Findings — all PASS (this is the headline fix).**

The switch is **global, DB-backed (`system_settings`), operator-only**
(`Permission.AUTOMATION_CONTROL` → `_ADMIN_ONLY` = `owner`/`admin`), and now wired
into every entry point:

- `WorkflowExecutionService.queue()` → `block_queue_if_paused()` → 409
  `automation.paused.queue_blocked` before any write.
- `WorkflowExecutionService.retry()` → `block_execution_if_paused()` → 409
  `automation.paused`.
- `WorkflowEventService.publish()` → 409 `automation.paused.queue_blocked` **before
  any write** (no event row, nothing queued).
- `ScheduleDispatcher.dispatch_due()` → early no-op returning zeroed stats; due
  ticks are claimed on the first sweep after resume.
- `ExecutionWorker.sweep()` → `_automation_enabled()` (fail-closed: a settings read
  failure is treated as paused and logged); when paused only `timeout_stuck()`
  runs, heartbeat continues, and the sweep returns `{"retried":0,"processed":0,
  "timed_out":N}`.
- Blocked responses embed the operator-supplied pause reason
  (`_paused_reason()` + `_with_reason()`).
- Pause/resume write `activity_logs` (`automation_paused`/`automation_resumed`) and
  bump `automation_paused_total`/`automation_resumed_total`.
- Endpoints: `GET /automation/status`, `POST /automation/pause`, `POST
  /automation/resume` (documented in `docs/api/endpoints/automation-control.md`).
- **Run-now** = `POST /workflow-executions` (the manual queue path, which is also
  the "run now" action); manual retry accepts `failed`, `cancelled`, and
  `timed_out`.

## 7. Audit & retention (plan §6)

**Source:** `retention_worker.py`, `config.py`, `docs/security.md`, runbooks.

**Findings — all PASS.**

- **Retention worker** (`python -m app.workers.retention_worker`, default
  `EXECUTION_RETENTION_ENABLED=true`): chunked delete of `execution_events` older
  than `EXECUTION_EVENT_RETENTION_DAYS` (default 90) and pruning of dead
  `worker_health` rows, both in `EXECUTION_RETENTION_BATCH` chunks; `activity_logs`
  never auto-deleted; `workflow_executions` kept by default. Metrics
  `retention_executions_deleted_total` / `retention_workers_pruned_total`.
- **Sanitized payloads:** adapter/error bodies are size-capped and stripped of
  stack traces (unified error envelope).

## 8. Performance hardening (plan §7)

Verified in §3 (fair drain, batch fetch, statement timeout, `(org, created_at
DESC)` index, `cancel_requested_at` partial index) and §4 (timeline indexes). No
long transactions: each sweep phase runs in its own session.

## 9. Database consistency

Model ↔ migration ↔ canonical schema ↔ Supabase policy parity swept:

- `WorkflowExecution.{cancel_requested_at,cancelled_by_user_id,idempotency_key}`
  == `0017` == `schema/workflows.sql`. ✅
- `ExecutionEvent`, `WorkerHealth`, `SystemSetting` models == `0017` ==
  `schema/{execution_events,worker_health,system_settings}.sql` (incl. triggers +
  RLS). ✅
- `execution_event_type` enum + `automation_paused/resumed` additions ==
  `migrations/enums/11_automation_hardening.sql` == `enums.py`. ✅
- Supabase policy files exist for the three new tables (RLS-only; service-role
  manages them). ✅
- `0017` is additive + idempotent (`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`),
  zero-data-loss, no table rewrites. ✅

## 10. Code-quality scan

- TODO/FIXME/HACK scan of every Phase 5C file: no real markers.
- No dead code or duplicated logic introduced. **No new backend runtime
  dependencies**; the only new frontend runtime dependency is
  `@tanstack/react-query` (used to back the new executions/monitoring data
  fetching), added to `package.json` and pinned in `package-lock.json`.
- Layering discipline held: thin endpoints → services → repositories → models;
  all settings live in `config.py` with boot-time validation.

## 11. Defects found & resolved during this audit

| ID | Finding | Severity | Resolution |
| -- | ------- | -------- | ---------- |
| F1 | The kill switch was **defined but inert** — no gate actually called `AutomationControlService`, so pausing did nothing. | **Critical** | Injected the control service into `WorkflowExecutionService`, `ScheduleDispatcher`, `WorkflowEventService`; gated `queue()`, `retry()`, `publish()`, `dispatch_due()`; gated the worker sweep with a fail-closed `_automation_enabled()`; added 409 codes with pause reason |
| F2 | Frontend permission map lacked `execution_*` keys (plan explicitly required them). | High | Added `execution_read/write/manage` to `lib/permissions.ts` (`manage` → `_ADMIN_ONLY`) |
| F3 | `schedule_dispatcher.py` and event tests exercised unpaused behavior only — the paused paths were untested. | Medium | Added pause/no-op + resumed-proceeds tests across dispatcher, event service, execution service, and worker |

## 12. Gates re-run (post-fix, from the current working tree)

| Gate | Result | Detail |
| ---- | ------ | ------ |
| Backend lint | ✅ | `ruff check app tests` — clean |
| Backend types | ✅ | `mypy app` — success (209 source files) |
| Backend tests | ✅ | **742 passed / 29 skipped** (integration tests needing a live DB run in CI with the Postgres service) |
| Frontend lint | ✅ | `eslint .` — 0 errors (1 pre-existing warning in `postcss.config.mjs`) |
| Frontend types | ✅ | `tsc --noEmit` — clean |
| Frontend format | ✅ | `prettier --check .` — all files compliant |
| Frontend tests | ✅ | vitest 96 passed |
| Frontend build | ✅ | `next build` — production build succeeds |

`docs/api/openapi.yaml` was regenerated from the live app (109 paths, incl. all
Phase 5C endpoints) and parses clean.

## 13. Risk register (residual)

| Risk | Level | Owner | Status |
| ---- | ----- | ----- | ------ |
| 29 DB-backed integration tests not run locally | Low | eng | Run in CI with the Postgres service; SQL mirrors kept in sync (§9) |
| At-least-once drain can re-deliver after a worker crash | Low | eng | Documented; workflows must be idempotent |
| `execution_events` grows until retention fires | Low | eng | Retention on by default + bounded chunks |
| Kill switch stops *new* automation, not in-flight runs | Low | ops | Documented in `security.md`; hard stop = terminate worker processes first |
| `pg_trgm`/new indexes add write amplification | Low | eng | Bounded column set; targeted hot paths |

## 14. Production deployment notes

1. Deploy migration `0017_automation_hardening.sql` (additive, idempotent; safe to
   re-run) and the new Supabase policy files before the app release.
2. No new backend runtime deps; one new frontend dep (`@tanstack/react-query`,
   pinned in `package-lock.json`); `backend/.env.example` already documents every
   Phase 5C setting (`EXECUTION_*`, `SCHEDULE_*`, `EVENT_*`, `RETENTION_*`).
3. Start the retention worker (`python -m app.workers.retention_worker`); the
   execution worker (`python -m app.workers.execution_worker`) runs as before.
4. Kill switch is admin-only (`AUTOMATION_CONTROL`); pausing blocks new work and
   the worker drains nothing until resume — use the documented runbook for deploys.

---

## Release Audit Certification — 🟢

**Verdict: PASS — CERTIFIED FOR PRODUCTION RELEASE**

- All eight Phase 5C items verified against the actual working tree at baseline
  `0b2b9c1`; no unimplemented backlog items.
- The critical F1 (inert kill switch) is fixed and end-to-end tested; the two
  high/medium gaps (F2 permission map, F3 paused-path test coverage) are closed.
- Every gate re-run green: backend 742 passed / 29 CI-only skips, `ruff` and
  `mypy` clean; frontend 96 tests, `eslint` 0 errors, `tsc` clean, `prettier`
  clean, `next build` succeeds.
- Migrations are additive and idempotent; no new backend runtime dependencies
  (the sole new frontend dep is pinned in `package-lock.json`); docs and the
  regenerated OpenAPI spec match the live API.
- **This batch is approved to ship.**
