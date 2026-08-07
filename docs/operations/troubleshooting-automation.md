# Operations — Troubleshooting Automation

Diagnostics for the automation engine. Follow the sections in order; each ends
with the specific gate/endpoint to confirm the fix.

## 1. Executions are not starting

Symptoms: `queue-status` shows a growing `queued` count, nothing is draining.

Check, in order:

1. **Is automation paused?** `GET /automation/status` — if `enabled=false`,
   the worker intentionally skips the queue. Pause blocks manual queue/retry
   with `409 automation.paused…`. Resume when appropriate.
2. **Is the execution worker running?** `monitoring/heartbeat-visibility` —
   a `stale` row for `worker_type=execution` means the loop is dead or never
   started (`python -m app.workers.execution_worker`).
3. **Is the worker healthy but empty?** `monitoring/worker-statistics` —
   `loop_ok=false` with a `last_error` points at a failing phase (look at the
   `agencyos.automation.worker` logs).
4. **Is the workflow active?** Executions queue only for `active` workflows;
   deactivated workflows are failed with `workflow_unavailable`.

## 2. Worker keeps restarting / sweeps fail

- Read `agencyos.automation.worker` logs; each phase is a separate transaction
  so a failure is scoped.
- Check `EXECUTION_STATEMENT_TIMEOUT_SECONDS`: a query timing out (usually a
  missing index after a large data import) surfaces as a phase error. Verify the
  Phase 5C indexes exist (`0017_automation_hardening.sql`):
  `(organization_id, created_at DESC)` and the `(organization_id, status)` list
  indexes.
- `SET LOCAL statement_timeout` applies per phase; it never fails the loop, it
  fails the phase — confirm with the heartbeat `loop_ok` field.

## 3. Executions stuck in `running`

The stale-timeout sweep (`timeout_stuck`) re-converges `running` rows older
than `EXECUTION_TIMEOUT_SECONDS` → `timed_out`. If rows stay `running`:

- Confirm the sweep runs: `monitoring/execution-history` filtered to
  `timed_out` should show recent conversions.
- A hung adapter is bounded by `asyncio.wait_for` inside `process_queued`, so a
  single stuck adapter cannot wedge the worker task.
- If executions are legitimately long-running, raise `EXECUTION_TIMEOUT_SECONDS`
  (and confirm the workflow's steps can tolerate it).

## 4. Retries are not happening

- Retries only re-fire while automation is **enabled**; while paused the retry
  phase is skipped (but nothing is lost — due retries are processed on resume).
- `process_retries` requeues `retrying` rows whose `next_retry_at` has elapsed;
  confirm the cadence (`EXECUTION_POLL_INTERVAL_SECONDS`) and that
  `monitoring/execution-statistics` shows `retrying` counts draining.
- Manual retry of `failed`/`cancelled`/`timed_out` is available via
  `POST /workflow-executions/{id}/retry`; it returns `409` while paused.

## 5. Schedule triggers do not fire

- Confirm `SCHEDULE_DISPATCHER_ENABLED=true` and the worker runs
  `schedule_tick` on `SCHEDULE_POLL_INTERVAL_SECONDS`.
- Check `monitoring/schedule-statistics`: `conflicts` growing means multiple
  workers contend (expected — the optimistic reservation means exactly one
  wins); `failed` growing means per-trigger queue errors (usually a
  deactivated workflow — check `agencyos.automation.schedule` logs).
- While paused, dispatch is a deliberate no-op; `tick_skipped_automation_paused`
  appears in the logs. Due ticks are claimed on the first sweep after resume.

## 6. Event-driven executions missing

- Publishing while paused returns `409 automation.paused.queue_blocked`; the
  event is **not** written, so nothing is silently lost — the publisher must
  retry after resume.
- `event_publish_total` counts publishes, `event_executions_queued` counts the
  fan-out. `event_fanout_truncated` non-zero means more than
  `EVENT_FANOUT_MAX_TRIGGERS` triggers matched and the excess was dropped —
  narrow the `event_type` match.
- A published event is `consumed=false` if no enabled trigger matched.

## 7. Timeline / history gaps

- `execution_events` writes are **best-effort**: a timeline failure never fails
  the execution. Expect occasional gaps under load; the `activity_logs`
  `EXECUTION_*` trail is the authoritative business record.
- Retention deletes `execution_events` older than
  `EXECUTION_EVENT_RETENTION_DAYS` (default 90) — "missing" old timeline rows
  are usually past the retention window, not lost.

## 8. Monitoring endpoints erroring

- `operational/summary` requires `automation_manage` (owner/admin); the rest
  require `automation_read`. A `403` is an RBAC problem, not an infra one.
- Cross-org endpoints read across tenants by design — they are operator-only.
  If you are seeing another tenant's data in a customer-facing context, that is
  a client using the wrong endpoint, not a leak.

## 9. Worker heartbeats missing entirely

- Heartbeats are written per loop iteration and on shutdown (best-effort). If
  `worker_health` is empty, the workers are not running in this environment or
  the retention worker pruned rows.
- The heartbeat row is upserted on `(worker_type, instance_id)`; multiple
  instances appear as multiple rows — that is expected.

## When to escalate

- Workers looping with `loop_ok=false` after a deploy.
- `execution_drained_total` at zero for an extended period with a healthy
  heartbeat and non-empty `queue-status`.
- `schedule_dispatch_failure` bursts or `reservation_conflict` spikes with a
  single worker.
- Credential rekey `failed` rows (see `docs/security.md`) or a persistently
  non-zero stale count after a key rotation.

Always attach the `request_id` (for API issues) and the worker phase logs when
filing a report.
