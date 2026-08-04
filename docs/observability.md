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

## Alerts worth adding

- Liveness/readiness failures (instance restarted or out of traffic).
- 5xx rate and p95/p99 latency per endpoint.
- DB pool exhaustion and failed DB connectivity checks.
- Rate-limit (429) spikes and auth failure bursts (possible abuse).
