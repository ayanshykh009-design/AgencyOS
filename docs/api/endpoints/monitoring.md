# Monitoring (Operational)

Visibility into the automation infrastructure and the organization's execution
queue. All endpoints are JWT-authenticated. Tenant data (executions, queue
depth, lifecycle events, delivery outbox) is **org-scoped to the caller** and
requires `automation_read` (all roles). Infrastructure views that disclose
hostnames, pids, and process counters are **admin-only** (`automation_manage`).

## GET /api/v1/monitoring/operational/summary

`automation_manage`. One-shot summary for an ops dashboard: execution counts,
worker health, automation status, schedule stats, and system/database health.

## GET /api/v1/monitoring/execution-statistics

`automation_read`. `hours` (1–168, default 24). Counts by execution status,
per-workflow distribution, and the caller's own organization distribution.

## GET /api/v1/monitoring/worker-statistics

`automation_manage` (admin-only — discloses hostnames/pids). `hours` (1–168,
default 24). Worker counts, health status, error distribution, and per-worker
detail from the heartbeat rows.

## GET /api/v1/monitoring/schedule-statistics

`automation_manage` (admin-only — process counters). `hours` (1–168, default
24). Schedule dispatcher outcomes in the window: queued, failed, skipped,
conflicts.

## GET /api/v1/monitoring/retention-statistics

`automation_manage` (admin-only — process counters). `hours` (1–168, default
24). Retention sweep outcomes: deleted `execution_events` and pruned
`worker_health` rows.

## GET /api/v1/monitoring/automation-lifecycle

`automation_read`. Counts of `automation_paused`/`automation_resumed`
`activity_logs` events for the caller's organization in the window plus the
current kill-switch status.

## GET /api/v1/monitoring/heartbeat-visibility

`automation_manage` (admin-only — discloses hostnames/pids). Per-instance
worker heartbeats.

| Query param          | Type | Notes                                          |
| -------------------- | ---- | ---------------------------------------------- |
| `worker_type`        | str? | Filter by type (`execution`, `credential`)     |
| `stale_within_seconds`| int | Staleness window (60–86400, default 300)       |
| `limit`              | int  | Max rows (1–1000, default 100)                 |

A worker whose `last_heartbeat_at` is older than the window is stale (a dead
loop or a worker that never started).

## GET /api/v1/monitoring/execution-timeline

`automation_read`. Recent `execution_events` for the caller's organization with
the workflow name and execution status/duration attached.

| Query param | Type | Notes                                      |
| ----------- | ---- | ------------------------------------------ |
| `hours`     | int  | Window (1–168, default 24)                 |
| `status`    | enum | Filter by execution status                 |
| `workflow`  | str? | Filter by workflow name (partial match)    |
| `limit`     | int  | Max events (1–500, default 100)            |

## GET /api/v1/monitoring/execution-history

`automation_read`. Paginated execution history for the caller's organization.

| Query param | Type | Notes                                      |
| ----------- | ---- | ------------------------------------------ |
| `page`      | int  | 1-based page (default 1)                   |
| `page_size` | int  | 1–200 (default 50)                         |
| `hours`     | int  | Window (1–168, default 24)                 |
| `status`    | enum | Filter by execution status                 |
| `workflow`  | str? | Filter by workflow name (partial match)    |

## GET /api/v1/monitoring/queue-status

`automation_read`. Pending/queued/running depth for the caller's
organization (feeds the fair-drain health view).

## GET /api/v1/monitoring/delivery-statistics

`automation_manage` (admin-only, consistent with operational summaries).
Delivery outbox counts for the caller's organization: `queued`,
`processing`, `retrying`, `delivered`, `failed`, `cancelled`, plus derived
`active` (queued/processing/retrying) and `terminal` (delivered/failed/
cancelled) totals.

## GET /api/v1/monitoring/monitoring-information

`automation_read`. System, database, worker, and queue information in one
payload. Queue depth is org-scoped; system/worker aggregates are
platform-wide infrastructure data (no tenant rows).

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
