# Deliveries (Outbox)

M6 outbox: every message enqueued for a user (dashboard, and later
email/whatsapp/push) lives here with an append-only timeline of provider
attempts. All endpoints are JWT-authenticated and org-scoped. Reads require
`delivery_read`; enqueueing requires `delivery_write`; `retry`/`cancel`
require `delivery_manage` (admin/owner only).

Platform-wide delivery counts (across all organizations) are exposed under
[monitoring](monitoring.md) as `delivery-statistics`.

## GET /api/v1/deliveries

List the organization's deliveries, newest first. Returns the standard `Page`
envelope (`items`, `total`).

| Query param          | Type   | Notes                                |
| -------------------- | ------ | ------------------------------------ |
| `status`             | enum   | `queued`, `processing`, `delivered`, `retrying`, `failed`, `cancelled` |
| `channel`            | enum   | `dashboard`, `email`, `whatsapp`, `push` |
| `recipient_user_id`  | uuid   | Optional, filter by recipient        |
| `limit`              | int    | 1–500, default 100                   |
| `offset`             | int    | Default 0                            |

A delivery row includes `subject`, `body`, `status`, `attempts`/`max_attempts`,
`next_attempt_at`, `last_error`, `scheduled_for`, `delivered_at`/`failed_at`/
`cancelled_at`, plus `provider_metadata` and the original `payload`.

## POST /api/v1/deliveries

Enqueue a new delivery. Returns 201 with the created row (status `queued`).
Rate-limited.

```json
{
  "channel": "dashboard",
  "recipient_user_id": "…",
  "subject": "New meeting booked",
  "body": "A meeting was booked with a prospect.",
  "action_url": "/leads/…",
  "max_attempts": 3
}
```

| Field             | Type    | Notes                                        |
| ----------------- | ------- | -------------------------------------------- |
| `channel`         | enum    | Required. `dashboard` is the only shipped provider; `email`/`whatsapp`/`push` fail closed |
| `recipient_user_id` | uuid? | Optional recipient                           |
| `notification_id` | uuid?   | Optional linked inbox row                    |
| `approval_request_id` | uuid? | Optional linked approval                     |
| `subject`         | string  | 1–500 chars                                  |
| `body`            | string  | Required                                     |
| `action_url`      | string? | Deep link for the recipient                  |
| `payload`         | object  | Free-form, default `{}`                      |
| `max_attempts`    | int?    | 1–10, default from config                    |
| `scheduled_for`   | datetime? | Defer processing until this time           |
| `idempotency_key` | string? | Optional; replay-safe enqueue               |

## GET /api/v1/deliveries/{delivery_id}

Fetch a single delivery.

| Error                  | Meaning                  |
| ---------------------- | ------------------------ |
| `404 delivery.not_found` | No such delivery in this organization |

## GET /api/v1/deliveries/{delivery_id}/events

Append-only timeline for a delivery: `queued`, `claimed`,
`provider_dispatched`/`provider_returned`, `delivered`, `retrying`, `failed`,
`cancelled`, `timed_out`, `recovery_guard`. Standard `Page` envelope.

| Query param | Type | Notes                  |
| ----------- | ---- | ---------------------- |
| `limit`     | int  | 1–200, default 100     |
| `offset`    | int  | Default 0              |

## POST /api/v1/deliveries/{delivery_id}/retry

`delivery_manage`. Manually retry a `failed`/`cancelled` delivery: it re-enters
`queued` and its attempt counters reset. Rate-limited.

| Error                       | Meaning                        |
| --------------------------- | ------------------------------ |
| `409 delivery.not_retryable`| Status is not failed/cancelled |

## POST /api/v1/deliveries/{delivery_id}/cancel

`delivery_manage`. Cancel a `queued`/`processing`/`retrying` delivery. A
`processing` delivery is flagged (`cancel_requested_at`) and lands on
`cancelled` when the worker returns; the others cancel immediately.
Rate-limited.

| Error                        | Meaning                     |
| ---------------------------- | --------------------------- |
| `409 delivery.not_cancellable` | Status is already terminal |

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
