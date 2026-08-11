# Monitoring (Operational)

Operator-level visibility into the automation infrastructure: execution
statistics, worker health/heartbeats, schedule and retention sweeps, the global
kill-switch lifecycle, and cross-organization queue depth. All endpoints are
JWT-authenticated; the operational summary is **admin-only** (`automation_manage`),
everything else requires `automation_read`.

> These endpoints are operator/instance-scoped (they read across organizations),
> unlike the org-scoped automation endpoints documented under
> [workflow-executions](workflow-executions.md).

## GET /api/v1/monitoring/operational/summary

`automation_manage`. One-shot summary for an ops dashboard: execution counts,
worker health, automation status, schedule stats, and system/database health.

## GET /api/v1/monitoring/execution-statistics

`automation_read`. `hours` (1–168, default 24). Counts by execution status,
per-workflow distribution, and per-organization distribution.

## GET /api/v1/monitoring/worker-statistics

`automation_read`. `hours` (1–168, default 24). Worker counts, health status,
error distribution, and per-worker detail from the heartbeat rows.

## GET /api/v1/monitoring/schedule-statistics

`automation_read`. `hours` (1–168, default 24). Schedule dispatcher outcomes in
the window: queued, failed, skipped, conflicts.

## GET /api/v1/monitoring/retention-statistics

`automation_read`. `hours` (1–168, default 24). Retention sweep outcomes:
deleted `execution_events` and pruned `worker_health` rows.

## GET /api/v1/monitoring/automation-lifecycle

`automation_read`. Counts of `automation_paused`/`automation_resumed`
`activity_logs` events in the window plus the current kill-switch status.

## GET /api/v1/monitoring/heartbeat-visibility

`automation_read`. Per-instance worker heartbeats.

| Query param          | Type | Notes                                          |
| -------------------- | ---- | ---------------------------------------------- |
| `worker_type`        | str? | Filter by type (`execution`, `credential`)     |
| `stale_within_seconds`| int | Staleness window (60–86400, default 300)       |
| `limit`              | int  | Max rows (1–1000, default 100)                 |

A worker whose `last_heartbeat_at` is older than the window is stale (a dead
loop or a worker that never started).

## GET /api/v1/monitoring/execution-timeline

`automation_read`. Recent `execution_events` across all organizations with the
workflow name and execution status/duration attached.

| Query param | Type | Notes                                      |
| ----------- | ---- | ------------------------------------------ |
| `hours`     | int  | Window (1–168, default 24)                 |
| `status`    | enum | Filter by execution status                 |
| `workflow`  | str? | Filter by workflow name (partial match)    |
| `limit`     | int  | Max events (1–500, default 100)            |

## GET /api/v1/monitoring/execution-history

`automation_read`. Paginated execution history across all organizations.

| Query param | Type | Notes                                      |
| ----------- | ---- | ------------------------------------------ |
| `page`      | int  | 1-based page (default 1)                   |
| `page_size` | int  | 1–200 (default 50)                         |
| `hours`     | int  | Window (1–168, default 24)                 |
| `status`    | enum | Filter by execution status                 |
| `workflow`  | str? | Filter by workflow name (partial match)    |

## GET /api/v1/monitoring/queue-status

`automation_read`. Per-organization pending/queued/running depth across all
organizations (feeds the fair-drain health view).

## GET /api/v1/monitoring/delivery-statistics

`automation_manage` (admin-only, consistent with operational summaries).
Platform-wide delivery outbox counts across all organizations: `queued`,
`processing`, `retrying`, `delivered`, `failed`, `cancelled`, plus derived
`active` (queued/processing/retrying) and `terminal` (delivered/failed/
cancelled) totals.

## GET /api/v1/monitoring/monitoring-information

`automation_read`. Comprehensive system, database, worker, and queue
information in one payload.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
