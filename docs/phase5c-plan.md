# Phase 5C — Harden the Automation Foundation (Implementation Plan)

Status: approved. This document is the authoritative scope for Phase 5C.

## Decisions locked in
1. **Pause/resume** = global instance kill switch (DB-backed, operator-only), not per-org.
2. **Execution history** = new append-only `execution_events` table (technical timeline) **+** complete the existing `activity_logs` `EXECUTION_*` business audit trail.
3. **UI** = extend existing pages minimally (no redesign, no full ops dashboard).

## Current state (grounding)
- `WorkflowExecution` carries `status`, `attempts`, `max_attempts`, `next_retry_at`, `retry_delay_seconds`, `retry_backoff`, `input/output/error` (JSONB), `started_at/finished_at`, `requested_by_user_id`, `trace_id`; indexes on `(org,status)`, `(org,workflow)`, partial `next_retry_at`, partial `trace_id`.
- `ExecutionStatus`: `queued|running|succeeded|failed|retrying|cancelled|timed_out`. No `PAUSED`.
- `WorkflowExecutionService` implements queue/start/retry/cancel/complete/fail/timeout + `get_queued`, `get_queued_for_retry`, `get_stuck_running`; optimistic transitions; writes some `ActivityLog` `EXECUTION_*` events (enum values all exist).
- `ExecutionWorker` phases: `process_retries` → `process_queued` → `timeout_stuck` → `schedule_tick`; per-phase sessions; multi-instance safe via optimistic transitions. No heartbeat.
- Adapters: `N8nAdapter` (webhook, 30s default timeout, `raise_for_status`, no body capture), `BuiltinAdapter` (deterministic, stateless). `execute()` returns payload; no hard timeout / no cancel contract.
- `config.py` has `EXECUTION_*`, `SCHEDULE_*`, `EVENT_*`, `BUILTIN_*`, `CREDENTIAL_REKEY_*` settings + `validate_runtime()`/`validate_for_production()` hooks.
- `metrics.py`: in-process monotonic counters + optional OTel mirror; counters only (no histogram), worker process not OTel-instrumented.
- API (`workflow_executions.py`): POST queue, GET list (filters + bounded pagination), GET `/{id}`, POST `/{id}/start|retry|complete|fail|cancel`; authz = `EXECUTION_READ` + `WORKFLOW_WRITE`; `complete`/`fail` take an unvalidated raw `dict` body; no status-leap guard on timeout.
- `activity_logs` is an immutable append-only business trail with `event_type` enum + `metadata` JSONB + `occurred_at`; `AUDIT_READ` admin endpoint exists.
- Frontend: executions page (status filter, Retry/Cancel, gated on `automation_write`), workflow detail "Recent Executions" card (limit 20, no actions). No detail view, no run-now, no auto-refresh, no health summary. Frontend permission map lacks `execution_*` keys.
- `timeout()` has a TOCTOU gap (no `WHERE status='running'` guard).

---

## 1. Workflow reliability
**Objective:** dependable state transitions; no lost/corrupt/raced executions; safe in-flight cancel; hard per-execution timeout; status-leap guards.

**Missing work:**
- Fix `timeout()` TOCTOU: `UPDATE ... SET status='timed_out' ... WHERE id=:id AND status='running'` (also guard in `cancel`).
- Add `cancel_requested_at` (+ `cancelled_by_user_id`) to the execution. Cancel sets the flag then transitions; the worker honors it (skip starting QUEUED with flag set; if RUNNING, treat post-`adapter.execute` return as cancelled when flag set).
- Hard timeout in-process: wrap `adapter.execute` in `asyncio.wait_for(EXECUTION_TIMEOUT_SECONDS)` inside `process_queued`; on timeout mark `timed_out` directly (terminal, no auto-retry) and record a `timeout_guard` event. Prevents a hung adapter from wedging a worker task until the next sweep.
- Status-leap guards: `complete()`/`fail()` only from RUNNING; if `cancel_requested_at` is set when an adapter returns, land on `cancelled` instead of `succeeded`.
- Capture n8n non-2xx response body in `N8nClient` (bounded, sanitized) so error metadata carries real diagnostics.
- Cap `complete`/`fail` payload bodies at `BUILTIN_MAX_RESULT_SIZE_BYTES` (reuse) with the unified error envelope.

**Files:** `workflow_execution_service.py`, `execution_worker.py`, `n8n_client.py`, `workflow_execution.py`, `workflow_execution.py` schema, `database/schema/workflow_executions.sql`, RLS mirror, migration SQL.

**Testing:** unit — timeout guard, cancel-flag races, hard-timeout marking, payload cap.

**Docs:** execution semantics (at-least-once), timeout/cancel behavior.

## 2. Queue hardening
**Objective:** bounded, observable, fair queue; no unbounded growth; no duplicate manual queues; depth visibility.

**Missing work:**
- `idempotency_key` (nullable) + partial unique index `(organization_id, idempotency_key) WHERE idempotency_key IS NOT NULL`; `queue()` rejects duplicates with `409`.
- Per-org pending cap `EXECUTION_MAX_PENDING_PER_ORG` (default 500); `queue()` refuses with `409` when exceeded (`EXECUTION_MANAGE` bypasses).
- Per-org fair drain in `process_queued` (detail in §7).
- Queue-depth visibility: computed stats endpoint (§4) + counters `execution_queued_total`, `execution_drained_total`, `execution_retried_total`, `execution_failed_total`, `execution_timed_out_total`, `execution_cancelled_total`.
- Document at-least-once drain semantics.

**Files:** `workflow_execution_service.py`, `workflow_execution.py` + `database/schema/workflow_executions.sql`, `metrics.py`, `workflow_executions.py` endpoint.

**Testing:** unit — idempotency 409, per-org cap bypass, counter increments; integration — partial unique index + RLS mirror.

## 3. Execution observability
**Objective:** append-only per-execution timeline, completed business audit writes, duration telemetry.

**Missing work:**
- **New table `execution_events`** (append-only): `id`, `organization_id`, `workflow_id`, `execution_id` (FK CASCADE), `attempt`, `event_type`, `occurred_at`, `metadata` JSONB (`duration_ms`, step name/index, input refs, error, actor, adapter). Indexes: `(execution_id, occurred_at)`, `(organization_id, workflow_id, occurred_at)`. New enum `execution_event_type`: `queued|started|adapter_dispatched|adapter_returned|step_started|step_completed|step_failed|retrying|succeeded|failed|cancelled|timed_out|timeout_guard`.
- ORM `ExecutionEvent` + `ExecutionEventRepository` (append + pageable query) + `ExecutionEventService`; event writes are **best-effort** (wrapped so a timeline failure never fails an execution).
- Wire writes at every transition in `WorkflowExecutionService` + worker adapter boundaries + `BuiltinAdapter` step hooks.
- **Complete the `activity_logs` trail**: guarantee `execution_queued/started/completed/failed/retried/cancelled` with metadata `{execution_id, workflow_id, trigger_id, actor, duration_ms}`.
- Duration: derive `duration_ms`; expose on `WorkflowExecutionRead`; add `execution_duration_seconds` histogram (in-process + OTel when enabled).
- Worker OTel spans guarded by `OTEL_ENABLED`.
- Retention for this table in §6.

**Files:** new `execution_event.py` model/repo/service; `database/schema/execution_events.sql`, `database/migrations/enums/execution_event_type.sql`, RLS policies; edits to service/worker/adapter/`builtin_execution.py`; `metrics.py`, `observability.py`.

**API:** `GET /workflow-executions/{id}/events` (`EXECUTION_READ`, pageable).

**Frontend:** timeline render in the execution detail panel.

**Testing:** unit — events per transition, best-effort isolation, duration; integration — append-only, RLS, cascade.

## 4. Automation monitoring
**Objective:** worker liveness + org-scoped automation stats surfaced via API and a minimal dashboard card.

**Missing work:**
- **New table `worker_health`**: `id`, `worker_type`, `instance_id`, `pid`, `hostname`, `last_heartbeat_at`, `loop_ok`, `last_error`, counters JSONB. Upsert each loop iteration; *stale* when older than `EXECUTION_POLL_INTERVAL_SECONDS × 3`. Heartbeat written on shutdown too.
- **Endpoints:** `GET /automation/stats` (`EXECUTION_READ`, org-scoped), `GET /automation/workers` (`EXECUTION_MANAGE`, instance-level), `GET /health/workers` (non-gating).
- Frontend: dashboard **Automation health card** polling ~15s, gated on `EXECUTION_READ`.
- Fix frontend permission map: add `execution_read/write/manage`.

**Files:** new `worker_health.py` model/repo, `monitoring_service.py`, `automation_monitoring.py` endpoint; `database/schema/worker_health.sql` + RLS; workers; frontend dashboard + services + `lib/permissions.ts`.

**Testing:** unit — heartbeat upsert/staleness, stats aggregation; API authz matrix; frontend vitest.

## 5. Operational controls
**Objective:** manual run (Run-now), manual retry (incl. timed_out/cancelled), safe cancel, global pause/resume kill switch.

**Missing work:**
- **Global kill switch:** new `system_settings` table (key/value) holding `automation.enabled` (+ `paused_by`, `paused_at`, `paused_reason`). Gates checked once per loop iteration/sweep:
  - worker loop: skip all queue/schedule phases while disabled (still heartbeat),
  - `schedule_dispatcher.dispatch_due()` and `workflow_event_service.publish()`: no-op while disabled,
  - manual `queue()`: `409` with the pause reason while disabled.
- **Endpoints:** `GET /automation/status` (`EXECUTION_READ`), `POST /automation/pause` + `POST /automation/resume` (`EXECUTION_MANAGE`), each writing `activity_logs` via new enum values `AUTOMATION_PAUSED`/`AUTOMATION_RESUMED`.
- **Run-now:** `POST /workflows/{id}/execute` (`WORKFLOW_WRITE`) → `service.queue(..., trigger_type=manual, requested_by)`.
- Manual retry: extend `retry()` to accept `timed_out`.

**Files:** new `automation_control_service.py`, `system_setting.py` model/repo, endpoints; `schedule_dispatcher.py`, `workflow_event_service.py` gates; `workflow_executions.py`; `enums.py` + enum DDL.

**Testing:** unit — each gate no-ops while paused; pause→resume; authz; integration — settings row + RLS; API — 409 while paused.

## 6. Audit & compliance
**Objective:** complete, immutable, actor-attributed audit evidence; sane retention; no stack-trace leaks.

**Missing work:**
- Finish `EXECUTION_*` + add `AUTOMATION_PAUSED/RESUMED` audit writes (§3/§5) with actor and before/after status in `metadata`.
- **Retention worker:** config-gated sweep (default `EXECUTION_RETENTION_ENABLED=true`): chunked `DELETE` of `execution_events` older than `EXECUTION_EVENT_RETENTION_DAYS` (default 90) and pruning of superseded `worker_health` rows; `activity_logs` never auto-deleted; `workflow_executions` kept by default. Metrics `retention_deleted_total`.
- Sanitize adapter/error payloads (cap length, strip secrets, never surface stack traces).

**Files:** new `retention_worker.py` (or `retention_tick`); `config.py` settings + validation; `docs/security.md`, runbooks.

**Testing:** unit — retention boundary/batch; integration — chunked delete respects batch + RLS.

## 7. Performance hardening
**Objective:** bounded, fair, index-backed sweeps; no long transactions; no N+1 in the worker.

**Missing work:**
- Fair drain: `process_queued` selects candidate orgs (`GROUP BY organization_id ORDER BY MIN(created_at) LIMIT EXECUTION_ORGS_PER_SWEEP`, default 20), then per-org batches within `EXECUTION_BATCH_SIZE`.
- Kill N+1: batch-fetch workflows (`get_many` by ids).
- Per-session `SET LOCAL statement_timeout` from `EXECUTION_STATEMENT_TIMEOUT_SECONDS` (default 30).
- New indexes: `workflow_executions (org, created_at DESC)`, `execution_events` indexes, `cancel_requested_at` partial where useful.
- Sweep telemetry: per-phase duration + rows.

**Files:** `execution_worker.py`, `workflow_execution_repository.py`, `database/schema/workflow_executions.sql`, `config.py`, `metrics.py`.

**Testing:** unit — fair-drain distribution, batch fetch, statement-timeout bounds.

## 8. Documentation
- `docs/phase5c-plan.md` (this plan).
- **Operations:** `docs/operations/admin-guide.md`, `docs/operations/troubleshooting-automation.md`.
- Update `docs/api/endpoints/workflow-executions.md`, `docs/api/endpoints/workflows.md`, `docs/observability.md`, `docs/database.md`, `docs/security.md`.
- Update `*.env.example` + config reference.

---

## Estimated implementation order
1. DB foundations (tables, enums, columns, indexes, ORM, repos, RLS mirror).
2. Reliability (TOCTOU, cancel flag, hard timeout, guards, n8n body capture, payload caps).
3. Timeline + audit wiring (event service + writes, activity_logs completion, duration).
4. Queue hardening (idempotency, per-org cap, fair drain, batch fetch, statement timeout, counters).
5. Worker heartbeat + retention sweeps.
6. Operational controls (run-now, pause/resume/status + gates).
7. Monitoring endpoints.
8. Telemetry (histogram + worker OTel).
9. Frontend minimal extensions.
10. Docs + env/config templates.
11. Full gates until GREEN.

## Estimated complexity
Medium overall.

## Risks & mitigations
- Cancel/return races — `cancel_requested_at` + guarded transitions + race tests.
- `asyncio.wait_for` interruptibility — builtin engine stateless/deterministic; timed_out terminal; at-least-once documented.
- Unbounded new tables — retention on by default + bounded chunks.
- Fair-drain ordering changes — tests updated.
- Frontend gating drift — permission map fixed in same change.

## Dependencies
Only Phase 5A/5B artifacts; no new third-party dependencies; no Phase 6 features.

## Intentionally deferred to Phase 6
- Distributed/Redis-backed queue + cross-instance locking.
- n8n in-flight cancellation via the n8n API.
- Per-step retry policies and step-level pause.
- Alerting/notifications on backlog or worker down.
- Full operations dashboard; in-app schedule-configuration UI; batch runs / run-compare; execution export/archive; schedule run-history visualization.
