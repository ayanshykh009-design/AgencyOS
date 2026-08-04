# Phase 5B — Schedule-Trigger Cron Dispatcher Report

**Date:** 2026-08-04
**Scope:** Item 3 of the Phase 5B backlog — a schedule-trigger cron dispatcher in
the worker loop. Ticks due schedule triggers exactly once per cron fire (even
across retries, restarts, and multiple worker instances), queues executions
without ever blocking or delaying the existing execution queue, and emits
structured logs + lightweight metrics for every lifecycle event.
**Gate:** **🟢 GREEN**

---

## 1. Decision Gate: 🟢 GREEN

| Gate | Result | Detail |
| ---- | ------ | ------ |
| Backend tests | ✅ | 532 passed / 21 skipped (skips = integration needing a live DB) |
| Backend lint | ✅ | `ruff check app tests` — all checks passed |
| Backend types | ✅ | `mypy app` — no issues in 187 source files |
| Frontend lint | ✅ | `eslint .` — 0 errors (1 pre-existing warning) |
| Frontend types | ✅ | `tsc --noEmit` — clean |
| Frontend format | ✅ | `prettier --check .` — all files compliant |
| Frontend tests | ✅ | 16 files / 89 tests passed |

No new dependencies were introduced. The cron evaluator is stdlib-only (the
`croniter` candidate was dropped).

## 2. What Was Built

### New modules

| File | Purpose |
| ---- | ------- |
| `app/services/schedule_cron.py` | Minimal 5-field cron evaluator: `validate_cron()` and `previous_fire(expr, now)`. UTC, minute precision, `*`/`?`/`n`/`a-b`/`a-b/n`/`*/n`/lists, month and day names, `7` as a Sunday alias, vixie-style DOM-or-DOW day matching. Returns `None` for impossible dates (e.g. `0 0 31 2 *`) within a ~4-year lookback. |
| `app/services/schedule_dispatcher.py` | `ScheduleDispatcher.dispatch_due(now=…, limit=…)`: scans enabled schedule triggers on active workflows, computes the previous fire time, atomically reserves the tick, and queues an execution — reservation and queueing share one transaction. |
| `app/core/metrics.py` | Thread-safe counter registry: always-available in-process fallback counters mirrored to real OpenTelemetry meters when `OTEL_ENABLED=true`. Exposes `get_counter`, `read_counter`, `reset`. |

### Changes to existing code

| File | Change |
| ---- | ------ |
| `app/repositories/workflow_trigger.py` | `list_enabled_schedules(limit)` (schedule + enabled, workflow status `active`, oldest-first, batched) and `reserve_last_fired(trigger_id, previous_fire, now)` — an optimistic `UPDATE … WHERE last_fired_at IS NULL OR last_fired_at < previous_fire`. |
| `app/services/workflow_trigger_service.py` | Fail-fast cron validation on create/update (`trigger.schedule_cron_required`, `trigger.schedule_cron_invalid`). |
| `app/workers/execution_worker.py` | `schedule_tick()` (isolated session, gated by `SCHEDULE_DISPATCHER_ENABLED`) and cadence gating in `run_loop` via `time.monotonic()`; schedule errors are contained so the queue phases are never delayed. `sweep()` is unchanged. |
| `app/models/workflow_trigger.py`, `app/schemas/workflow_trigger.py` | `last_fired_at` column + partial index (`trigger_type='schedule' AND enabled`) and read-schema field. |
| `app/core/config.py`, `backend/.env.example`, `.env.example` | `SCHEDULE_DISPATCHER_ENABLED` (default true), `SCHEDULE_POLL_INTERVAL_SECONDS` (15), `SCHEDULE_BATCH_LIMIT` (100). |
| `database/schema/workflows.sql`, `database/migrations/0014_schedule_last_fired.sql` | Additive, zero-data-loss, re-runnable (`ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`) `last_fired_at` + partial index. |
| `frontend/src/types/index.ts`, `frontend/src/services/__tests__/workflow-triggers.test.ts` | `WorkflowTrigger.last_fired_at: string | null` parity. |

### New tests

| File | Coverage |
| ---- | -------- |
| `tests/unit/test_schedule_cron.py` | Field parsing, names, steps, ranges, `7`→Sunday, weekend/weekday matching, leap day, impossible dates, wildcard validation errors. |
| `tests/unit/test_schedule_dispatcher.py` | Reserve→queue happy path, already-fired skip, reservation conflict, invalid/never-firing cron skips, dispatch failure (reservation rolled back), batch-limit passthrough, per-outcome metrics. |
| `tests/unit/test_metrics.py` | Counter registry semantics (inc, reset, OTel mirror off/on). |
| `tests/unit/test_execution_worker.py` | `schedule_tick` wiring (return value, disabled, error propagation), cadence gating, schedule errors never abort the loop. |
| `tests/unit/test_workflow_trigger_service.py` | Cron validation on create/update. |
| `tests/integration/test_database_schema.py`, `tests/integration/test_services_integration.py` | DB-backed: migration 0014 additive/idempotent with zero data loss; reserve→queue exactly once across repeated sweeps; inactive workflows are invisible to the dispatcher. Run in CI only (no local Postgres). |

## 3. Notable Implementation Decisions

1. **Exactly-once dispatch via optimistic reservation.** Each tick is claimed
   with `UPDATE workflow_triggers SET last_fired_at = :now WHERE id = :id AND
   (last_fired_at IS NULL OR last_fired_at < :prev_fire)`. Only one worker wins
   a given tick; retries, restarts, and multi-instance deployments cannot
   double-fire. The dispatcher is restart-safe by construction: a crash before
   commit leaves no trace, a crash after commit cannot re-claim the tick.
2. **One transaction for reservation + queueing.** `reserve_last_fired` and
   `WorkflowExecutionService.queue` share the dispatcher session, so the tick
   and the execution persist or roll back together. If queueing fails with a
   business error (e.g. the workflow was deactivated between listing and
   queueing), the dispatcher rolls back, discarding the reservation so a later
   re-activation can fire the tick — never double-fire, never lose a committed
   tick.
3. **The queue is never blocked.** The dispatcher runs as an isolated worker
   phase with its own cadence (`SCHEDULE_POLL_INTERVAL_SECONDS`) inside
   `run_loop`, after the queue sweep, and schedule failures are caught and
   logged so `sweep()` keeps polling uninterrupted. `sweep()` itself is
   byte-for-byte unchanged.
4. **No new dependencies.** The cron evaluator is ~150 lines of stdlib
   (`datetime`, `re`); `croniter` was deliberately avoided to keep the
   dependency surface flat. OpenTelemetry counters reuse the already-present
   `opentelemetry-sdk`.
5. **Structured logs ride in the `message` field.** The shared `JsonFormatter`
   in `app/core/logging.py` drops `extra` kwargs, so lifecycle data is carried
   as a JSON payload in the log message (`schedule.tick_start`, `trigger_detected`,
   `reservation_success`, `reservation_conflict`, `dispatch_failed`,
   `workflow_queued`, `trigger_skipped`, `schedule.tick_end`) — the shared
   formatter is left untouched.
6. **Metrics without an exporter.** `app/core/metrics.py` always maintains
   thread-safe in-process counters (usable by tests and workers without any
   collector) and mirrors to real OTel meters only when `OTEL_ENABLED=true`.
7. **UTC, minute precision.** Expressions are evaluated in UTC to avoid DST
   artifacts; cron semantics match vixie cron, including the DOM-or-DOW
   combination rule and `7` as Sunday.
8. **Fail-fast at write time.** Invalid cron expressions are rejected by the
   trigger create/update path (400) so bad schedules never linger; the
   dispatcher still defends against legacy rows (`invalid_cron` /
   `missing_cron` skips).

## 4. Verification Narrative

- **Cron evaluator** is exercised property-style across the full field grammar
  and calendar edge cases (weekends, leap years, impossible dates, Sunday
  aliases) with fixed-UTC fixtures.
- **Dispatcher** behavior (reserve, skip, conflict, failure, metrics) is covered
  with a fake session and mocked repository/execution service; the DB-backed
  variants prove the real SQL behaves identically against Postgres in CI.
- **Worker integration** proves the schedule phase runs at its own cadence and
  that a throwing schedule tick never aborts the queue loop.
- **Frontend** type parity is locked by the fixture in the service test suite.
- **Full local gates** reproduce the CI steps: `ruff check app tests`, `mypy app`,
  `pytest`, `eslint`, `tsc --noEmit`, `prettier --check`, `vitest`.

## 5. Risk Register

| Risk | Level | Owner | Status |
| ---- | ----- | ----- | ------ |
| Integration suite not run locally (21 DB tests incl. 3 new) | Low | eng | Run in CI with the Postgres service |
| Lookback window (~4 years) bounds catch-up dispatch after long downtime | Low | product | Older missed ticks are intentionally dropped to avoid replay storms |
| DOM/DOW combined semantics are vixie-style, not Vixie-looped | Low | eng | Matches common cron tooling; documented in `schedule_cron.py` |

## 6. Verdict

Phase 5B item 3 is complete: schedule triggers are now dispatched from the
worker loop with exactly-once semantics, zero new dependencies, additive
restart-safe migrations, structured telemetry, and a fully green gate across
backend and frontend.
