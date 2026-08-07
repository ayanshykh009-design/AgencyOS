# Operations — Admin Guide

Runbook for AgencyOS operators. Covers the automation kill switch, worker
lifecycle, retention, and the monitoring surface. API examples use
`curl` with `$TOKEN` as an admin JWT.

## Automation kill switch

The global pause/resume switch stops **all** automation instance-wide
(queueing, retries, schedule dispatch, and event-driven execution) without
dropping data. In-flight executions finish or time out normally; queued work is
preserved and drains on resume.

```bash
# Status
curl -H "Authorization: Bearer $TOKEN" https://api.example.com/api/v1/automation/status

# Pause (admin only) — supply a reason; it is audited and surfaced in 409s
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"reason":"n8n maintenance"}' https://api.example.com/api/v1/automation/pause

# Resume
curl -X POST -H "Authorization: Bearer $TOKEN" https://api.example.com/api/v1/automation/resume
```

While paused:

- manual queue/retry and event publish return `409 automation.paused…` with the
  reason in the message;
- the execution worker skips its retry and queue-drain phases (heartbeats and
  stale-timeout housekeeping continue, so the instance stays healthy);
- schedule dispatch is a no-op; due ticks are claimed on the first sweep after
  resume (no missed fire).

Every pause/resume writes an `activity_logs` row (`automation_paused` /
`automation_resumed`) with the acting operator and reason. Use the
`automation-lifecycle` monitoring endpoint to audit recent toggles.

## Worker lifecycle

Automation workers run as standalone loops:

| Worker             | Entrypoint                              | Purpose |
| ------------------ | --------------------------------------- | ------- |
| Execution worker   | `python -m app.workers.execution_worker` | Requeues due retries, drains the queued bucket through the adapters, re-converges stale `running` rows, dispatches due schedule ticks |
| Retention worker   | `python -m app.workers.retention_worker` | Deletes expired `execution_events` and prunes dead `worker_health` rows, in chunks |
| Credential rekey   | `python -m app.workers.credential_worker`| Re-encrypts credential values under the current key after rotation |

Each phase runs in its own session/transaction, is restart-safe (state lives in
Postgres), and may run on multiple instances — transitions are optimistic, so
exactly one worker wins each claim.

**Heartbeats.** Every loop iteration upserts a `worker_health` row
(`worker_type`, `instance_id`, `pid`, `hostname`, `loop_ok`, `last_error`,
counters). A row older than `EXECUTION_POLL_INTERVAL_SECONDS × 3` is *stale*.
Watch `monitoring/heartbeat-visibility` (default 300s staleness window) and
`monitoring/worker-statistics` to detect dead or flapping workers.

**Scaling.** Run the execution worker on as many instances as the queue needs;
the schedule and retention phases are contained per instance and never delay
the queue. Do **not** run a second instance of the credential rekey worker
with a different key version mid-rotation.

## Execution & queue

- **Fair drain.** Each sweep visits up to `EXECUTION_ORGS_PER_SWEEP` orgs
  (oldest-first) and drains `EXECUTION_BATCH_SIZE` per org, so one busy org
  cannot starve the rest. Watch `monitoring/queue-status` for depth.
- **Pending cap.** `queue()` refuses with `409 execution.pending_cap_exceeded`
  once an org has `EXECUTION_MAX_PENDING_PER_ORG` (default 500) un-drained
  executions. Users with `automation_manage` bypass the cap.
- **Idempotency.** Manual/event submissions can set `idempotency_key`; the
  partial unique index `(organization_id, idempotency_key)` guarantees at-most-
  once queueing for that key.
- **Timeouts.** `EXECUTION_TIMEOUT_SECONDS` (default 300) bounds a single run;
  hung adapters are killed by `asyncio.wait_for` and the execution is marked
  `timed_out` (terminal). Per-session `EXECUTION_STATEMENT_TIMEOUT_SECONDS`
  bounds sweep queries so a runaway sweep never pins a DB connection.

## Retention

Retention is on by default (`EXECUTION_RETENTION_ENABLED=true`):

- `execution_events` older than `EXECUTION_EVENT_RETENTION_DAYS` (default 90)
  are deleted in chunks of `EXECUTION_RETENTION_BATCH` (default 1000);
- superseded `worker_health` rows are pruned the same way;
- `activity_logs` and `workflow_executions` are **never** auto-deleted.

Confirm sweeps run via `monitoring/retention-statistics`
(`retention_executions_deleted_total`, `retention_workers_pruned_total`).

## Monitoring surface

All under `monitoring/` (see [endpoints](../api/endpoints/monitoring.md)):

| Endpoint | What it answers |
| -------- | --------------- |
| `operational/summary` | One-shot ops dashboard snapshot (admin) |
| `execution-statistics` | Status/workflow/org breakdown in a window |
| `worker-statistics` | Worker health + error distribution |
| `schedule-statistics` | Dispatch queued/failed/skipped/conflicts |
| `retention-statistics` | Retention sweep outcomes |
| `automation-lifecycle` | Pause/resume history + current status |
| `heartbeat-visibility` | Per-instance liveness (staleness window) |
| `execution-timeline` | Latest execution events, cross-org |
| `execution-history` | Paginated cross-org execution history |
| `queue-status` | Per-org queue depth |
| `monitoring-information` | System/DB/worker/queue roll-up |

## Runbook: pausing for a deployment

1. `POST /automation/pause` with a reason (stops new work immediately).
2. Deploy/migrate; the worker stays alive and healthy while paused.
3. Verify with `GET /automation/status` and `monitoring/heartbeat-visibility`.
4. `POST /automation/resume`; confirm `monitoring/queue-status` drains and
   `schedule-statistics` resumes counting.

## Environment reference

All tunables are documented in `backend/.env.example` and validated at boot
(`app/core/config.py`). Production config refuses to boot with unsafe values
(e.g. missing `SECRET_KEY`, `CREDENTIALS_ENC_KEY`, or disabled CSP).
