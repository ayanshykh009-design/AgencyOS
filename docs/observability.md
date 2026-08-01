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

## Alerts worth adding

- Liveness/readiness failures (instance restarted or out of traffic).
- 5xx rate and p95/p99 latency per endpoint.
- DB pool exhaustion and failed DB connectivity checks.
- Rate-limit (429) spikes and auth failure bursts (possible abuse).
