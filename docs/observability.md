# Observability Guide

The foundation ships with structured logs, request IDs, health endpoints, and
optional OpenTelemetry tracing. Centralize everything in staging/production.

## Logging

- **Dev:** human-readable console output.
- **Prod (`APP_ENV=production`):** one JSON object per line, including
  `ts`, `level`, `logger`, `request_id`, `message`, and optional `exc`.
- File output is opt-in via `LOG_TO_FILE=true` (rotated, 5 MB × 3 files).

Ship JSON logs to an aggregator (Datadog, CloudWatch, Loki…) and query by
`request_id` to correlate a single request across log lines.

## Request IDs

- Every request receives/echoes an `X-Request-ID` header.
- The id is propagated through async code via `contextvars` and included in
  every log record for that request — use it when debugging client reports.

## Health probes

- `GET /api/v1/health/live` — process liveness (used for restarts).
- `GET /api/v1/health/ready` — dependency readiness (DB reachability;
  used by load balancers / orchestrators to control traffic).
- `GET /api/v1/health` — alias for liveness (backward compatible).

Wire these into your orchestrator (Docker healthchecks are already defined in
the compose files; Kubernetes should use `/ready`).

## Metrics & traces (OpenTelemetry)

Enabled by setting:

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=agencyos-api
OTEL_ENDPOINT=http://otel-collector:4318/v1/traces
```

FastAPI requests are auto-instrumented and spans are exported via OTLP/HTTP.
Send them to an OTLP collector and forward to your tracing backend (Jaeger,
Datadog, Grafana Tempo, …). Metric and log exporters can be added in
`app/core/observability.py` as the stack grows.

## Schedule dispatcher telemetry

The schedule dispatcher (worker phase `ExecutionWorker.schedule_tick`) emits one
structured JSON log line per lifecycle event (logger
`agencyos.automation.schedule`) with the event name in the `message` field:
`schedule.tick_start`, `trigger_skipped` (reason: `missing_cron` / `invalid_cron`
/ `cron_never_fires` / `not_due`), `trigger_detected`, `reservation_success`,
`reservation_conflict`, `dispatch_failed`, `workflow_queued`, and
`schedule.tick_end`.

It also maintains lightweight counter metrics via `app/core/metrics.py` —
always-available in-process fallback counters, mirrored to real OpenTelemetry
meters when `OTEL_ENABLED=true`:

| Counter                      | Meaning                                            |
| ---------------------------- | -------------------------------------------------- |
| `schedule_dispatch_success`  | Ticks claimed and dispatched (execution queued)    |
| `schedule_dispatch_failure`  | Ticks whose dispatch failed                        |
| `schedule_dispatch_skip`     | Triggers skipped (not due / invalid cron)          |
| `reservation_conflict`       | Ticks already claimed by another worker            |
| `queue_success`              | Executions queued by the dispatcher                |
| `queue_failure`              | Executions that failed to queue                    |

Use the dispatch counters to alert on `schedule_dispatch_failure` bursts and to
confirm every tick dispatches exactly once (`reservation_conflict` should stay
near zero; spikes mean overlapping worker schedules).

## Credential rekey telemetry

The credential rekey worker (`CredentialWorker.rekey_tick`, run via
`python -m app.workers.credential_worker`) emits a structured JSON log line per
sweep (logger `agencyos.automation.credential_worker`) with `rekeyed` and
`stale` counts, plus per-row failure logs when a value cannot be decrypted
(those rows are left untouched for manual handling). It maintains the same
counter metrics as the dispatcher:

| Counter                    | Meaning                                        |
| -------------------------- | ---------------------------------------------- |
| `credential_rekey_processed` | Credential values re-encrypted under the current key |
| `credential_rekey_failed`    | Rows skipped because decryption failed (corruption) |

Alert on `credential_rekey_failed` (data corruption or a missing previous key
during rotation) and on a persistently non-zero `stale` count after a master
key rotation (the dual-read window is open until rekey completes).

## Builtin execution telemetry

The `builtin` execution adapter (`app/services/execution_adapter.py`) logs a
structured line per run (logger `agencyos.automation.adapter`) with the
execution/workflow ids and the outcome, and maintains the same counter metrics:

| Counter                     | Meaning                                    |
| --------------------------- | ------------------------------------------ |
| `builtin_execution_started` | Builtin workflow executions started        |
| `builtin_execution_succeeded` | Builtin workflow executions that succeeded |
| `builtin_execution_failed`  | Builtin workflow executions that failed    |

A rising `builtin_execution_failed` rate signals a misconfigured definition
(guards/templates fail at runtime); step-level errors surface in the execution
`error` payload. `builtin_execution_started` should track the queued execution
rate for builtin workflows — divergence means executions are not being drained.

## Workflow event telemetry

The event service (`app/services/workflow_event_service.py`) emits the same
counter metrics on publish:

| Counter                    | Meaning                                        |
| -------------------------- | ---------------------------------------------- |
| `event_publish_total`      | Workflow events published                       |
| `event_executions_queued`  | Executions queued by event fan-out             |
| `event_fanout_truncated`   | Events whose fan-out hit the trigger limit     |

Alert on `event_fanout_truncated` — a persistent non-zero value means an
`event_type` matches far more enabled triggers than intended and executions are
being silently dropped at the cap.

## Execution worker telemetry

The execution worker (`app/workers/execution_worker.py`) emits per-phase
telemetry. The `execution_worker_phase_seconds` histogram records the duration
of each sweep phase (`retries`, `queued`, `timeouts`, `schedule`) so a slow
phase is visible even when the loop is healthy. Counter metrics:

| Counter                     | Meaning                                          |
| --------------------------- | ------------------------------------------------ |
| `execution_queued_total`    | Executions queued (all entry points)             |
| `execution_drained_total`   | Executions drained from the queue                |
| `execution_retried_total`   | Executions requeued by the retry phase           |
| `execution_failed_total`    | Executions failed                                 |
| `execution_timed_out_total` | Executions marked timed out (stale/hard timeout) |
| `execution_cancelled_total` | Executions cancelled                              |

The worker snapshots these counters into its `worker_health` heartbeat row each
loop iteration, so `monitoring/heartbeat-visibility` shows a live counter view
per instance. A `drained` counter that stops growing while `queue-status` shows
depth means the worker is paused, dead, or stuck (see
`docs/operations/troubleshooting-automation.md`).

## Worker heartbeats & retention telemetry

Every worker loop iteration upserts a `worker_health` row
(`worker_type`, `instance_id`, `pid`, `hostname`, `loop_ok`, `last_error`,
counters) — and once more on shutdown. `loop_ok=false` with a `last_error`
marks the loop's last phase as failed. Surface this via:

- `GET /api/v1/monitoring/heartbeat-visibility` — per-instance rows with a
  configurable staleness window (default 300s).
- `GET /api/v1/monitoring/worker-statistics` — aggregate health + errors.
- `GET /api/v1/monitoring/automation-lifecycle` — kill-switch pause/resume
  history (from `activity_logs`) plus current status.

The retention worker (`app/workers/retention_worker.py`) reports its sweeps:

| Counter                              | Meaning                                        |
| ------------------------------------ | ---------------------------------------------- |
| `retention_executions_deleted_total` | `execution_events` rows deleted in the window  |
| `retention_workers_pruned_total`     | Dead `worker_health` rows pruned               |

Alert on a persistent zero across both counters with retention enabled — the
sweep has stopped and `execution_events` will grow unbounded.

The memory cleanup worker (`app/workers/memory_worker.py`) reports its sweeps
(see [endpoints](api/endpoints/memory.md#memory-cleanup-worker)):

| Counter                              | Meaning                                     |
| ------------------------------------ | ------------------------------------------- |
| `agencyos.memory.cleanup.expired_total` | Expired `working` memories deleted (org-scoped chunks) |

Its tick duration is recorded in the histogram
`agencyos.memory.cleanup.duration_seconds`. Alert on a persistent zero counter
with `MEMORY_CLEANUP_ENABLED=true` — expired `working` memory will grow
unbounded.

## Alerts worth adding

- Liveness/readiness failures (instance restarted or out of traffic).
- 5xx rate and p95/p99 latency per endpoint.
- DB pool exhaustion and failed DB connectivity checks.
- Rate-limit (429) spikes and auth failure bursts (possible abuse).
- Worker heartbeat stale (`loop_ok=false` or `last_heartbeat_at` older than
  `EXECUTION_POLL_INTERVAL_SECONDS × 3`).
- `execution_drained_total` flat while `queue-status` depth is non-zero.
- `schedule_dispatch_failure` bursts and `event_fanout_truncated` non-zero.
