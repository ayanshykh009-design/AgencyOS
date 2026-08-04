# Workflow Executions

Org-scoped execution history with a queued → running → terminal state machine,
automatic retries, and manual retry/cancel. All endpoints are JWT-authenticated.
Reads require `automation_read`, writes `automation_write`.

## States

`queued` → `running` → `succeeded` | `failed` | `cancelled` | `timed_out`.
Failed executions schedule retries through `retrying` until `max_attempts` is
exhausted, after which they stay `failed`.

## POST /api/v1/workflow-executions

Queue an execution for a workflow. Returns 201 with the new execution id.

```json
{
  "organization_id": "…",
  "workflow_id": "…",
  "trigger_id": null,
  "input": {},
  "max_attempts": 3,
  "retry_delay_seconds": 60,
  "retry_backoff": "exponential",
  "trace_id": null
}
```

`max_attempts` 1–10, `retry_delay_seconds` ≥ 0, `retry_backoff` `constant` or
`exponential`. Response: `{execution_id, status}` (status is `queued`).

## GET /api/v1/workflow-executions

List executions. Paginated with `limit` (1–200, default 50) and `offset`.

| Query param  | Type  | Notes                                  |
| ------------ | ----- | -------------------------------------- |
| `status`     | enum  | `queued`, `running`, `succeeded`, `failed`, `retrying`, `cancelled`, `timed_out` |
| `workflow_id` | UUID | Executions for one workflow            |

## GET /api/v1/workflow-executions/{execution_id}

Fetch one execution.

## POST /api/v1/workflow-executions/{execution_id}/start

Transition `queued` → `running` and stamp `started_at`. Typically invoked by the
execution worker.

## POST /api/v1/workflow-executions/{execution_id}/complete

Mark an execution succeeded. Body is the workflow output dict.

## POST /api/v1/workflow-executions/{execution_id}/fail

Mark an execution failed. Body is an error dict (e.g. `{message, detail}`).
Query param `schedule_retry` (default `true`) controls whether a retry is
scheduled if attempts remain.

## POST /api/v1/workflow-executions/{execution_id}/retry

Manually retry a `failed` execution: resets to `queued` with a fresh attempt
budget (up to the workflow's `max_attempts`).

## POST /api/v1/workflow-executions/{execution_id}/cancel

Cancel a `queued` or `running` execution.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
