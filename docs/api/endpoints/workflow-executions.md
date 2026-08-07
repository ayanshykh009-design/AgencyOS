# Workflow Executions

Org-scoped execution history with a queued → running → terminal state machine,
automatic retries, a hard per-execution timeout, and manual retry/cancel. All
endpoints are JWT-authenticated. Reads require `automation_read`, writes
`automation_write`.

## States

`queued` → `running` → `succeeded` | `failed` | `cancelled` | `timed_out`.
Failed executions schedule retries through `retrying` until `max_attempts` is
exhausted, after which they stay `failed`. A running execution that exceeds
`EXECUTION_TIMEOUT_SECONDS` (default 300) is marked `timed_out` by the worker
(terminal — no auto-retry).

Draining is **at-least-once**: a worker crash mid-execution leaves the row
`running`, and the stale-timeout sweep re-converges it. Duplicate delivery of
an execution is possible after a crash; workflows must be idempotent.

## POST /api/v1/workflow-executions

Queue an execution (this is also the "run now" path for manual execution).
Returns 201 with the new execution id.

```json
{
  "organization_id": "…",
  "workflow_id": "…",
  "trigger_id": null,
  "input": {},
  "idempotency_key": null,
  "max_attempts": 3,
  "retry_delay_seconds": 60,
  "retry_backoff": "exponential",
  "trace_id": null
}
```

`max_attempts` 1–10, `retry_delay_seconds` ≥ 0, `retry_backoff` `constant` or
`exponential`. `idempotency_key` is optional; when set, it is unique per
organization and the queue is rejected with `409` if a row already exists with
the same key (prevents double-submission of manual/event-triggered runs).
Response: `{execution_id, status}` (status is `queued`).

| Error | Meaning |
| ----- | ------- |
| `404` `workflow.not_found` | The workflow does not exist in this org |
| `400` `workflow.not_active` | The workflow is not `active` |
| `409` `execution.pending_cap_exceeded` | `EXECUTION_MAX_PENDING_PER_ORG` reached (`automation_manage` bypasses) |
| `409` `execution.duplicate_idempotency` | `idempotency_key` already queued for this org |
| `409` `automation.paused.queue_blocked` | Automation is paused (kill switch) — message includes the pause reason |

## GET /api/v1/workflow-executions

List executions. Paginated with `limit` (1–200, default 50) and `offset`.

| Query param  | Type  | Notes                                  |
| ------------ | ----- | -------------------------------------- |
| `status`     | enum  | `queued`, `running`, `succeeded`, `failed`, `retrying`, `cancelled`, `timed_out` |
| `workflow_id` | UUID | Executions for one workflow            |
| `trigger_id` | UUID  | Executions for one trigger             |
| `sort`       | str   | `created_at` (default), `started_at`, `finished_at`, `status` |
| `order`      | str   | `asc` or `desc` (default `desc`)       |

## GET /api/v1/workflow-executions/{execution_id}

Fetch one execution.

## GET /api/v1/workflow-executions/{execution_id}/events

Fetch the append-only technical timeline for an execution (the `execution_events`
table). Paginated with `limit` (1–200, default 100) and `offset`. Each event
carries `event_type` (e.g. `queued`, `started`, `adapter_dispatched`,
`adapter_returned`, `step_started`, `step_completed`, `step_failed`,
`retrying`, `succeeded`, `failed`, `cancelled`, `timed_out`, `timeout_guard`),
`attempt`, `occurred_at`, and `metadata` (duration, step, error, actor…).
Timeline writes are best-effort — they never fail the execution they describe.

## POST /api/v1/workflow-executions/{execution_id}/start

Transition `queued` → `running` and stamp `started_at`. Typically invoked by the
execution worker. Optimistic: only one caller can win the transition.

## POST /api/v1/workflow-executions/{execution_id}/complete

Mark a `running` execution succeeded. Body is the workflow output dict, capped
at `BUILTIN_MAX_RESULT_SIZE_BYTES` (`413 execution.payload_too_large` above the
cap). If a cancel was requested mid-run, the execution lands on `cancelled`
instead of `succeeded`.

## POST /api/v1/workflow-executions/{execution_id}/fail

Mark a `running` execution failed. Body is an error dict (e.g.
`{message, detail}`). Query param `schedule_retry` (default `true`) controls
whether a retry is scheduled if attempts remain. Error payloads are sanitized
(bounded size, no secrets/stack traces).

## POST /api/v1/workflow-executions/{execution_id}/retry

Manually retry a `failed`, `cancelled`, or `timed_out` execution: resets to
`queued` with a fresh attempt budget (up to the workflow's `max_attempts`).

| Error | Meaning |
| ----- | ------- |
| `409` `execution.invalid_state` | Execution is not in a retryable state |
| `409` `automation.paused` | Automation is paused (kill switch) |

## POST /api/v1/workflow-executions/{execution_id}/cancel

Cancel a `queued`, `retrying`, or `running` execution. Queued/pending states
transition immediately; a running execution is flagged (`cancel_requested_at`)
and the worker lands it on `cancelled` when the adapter returns.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
