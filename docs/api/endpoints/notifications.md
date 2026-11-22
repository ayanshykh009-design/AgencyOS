# Notifications

Per-user in-app inbox; M6 delivery workers create and deliver inbox rows. All
endpoints are JWT-authenticated. Reads (and mark-read mutations) require
`notification_read`.

**There is no notification-create endpoint.** Every `NotificationType` is a
system/worker/agent/approval origin; inbox rows are created exclusively by
trusted internal paths (the M6 delivery worker via the in-app provider, and
internal services through `NotificationService.create`). The previous
`POST /api/v1/notifications` route was removed: a user-writable create
surface would let any authenticated member fabricate privileged
SYSTEM/approval notifications in another user's inbox.

## GET /api/v1/notifications

List the current user's notifications, newest first.

| Query param   | Type   | Notes                      |
| ------------- | ------ | -------------------------- |
| `only_unread` | bool   | Default false              |
| `limit`       | int    | 1–500, default 100         |
| `offset`      | int    | Default 0                  |

## GET /api/v1/notifications/unread-count

Unread badge count for the current user.

## GET /api/v1/notifications/counts

Notification counts grouped by `type`.

## POST /api/v1/notifications

Create a notification (system/worker writes). Returns 201. `user_id` is
optional; when omitted the row is org-scoped only.

## GET /api/v1/notifications/{notification_id}

Fetch a notification owned by the current user.

## PATCH /api/v1/notifications/{notification_id}

Update `is_read` (mark read **or** unread). Requires `is_read` in the body.

```json
{"is_read": true}
```

## POST /api/v1/notifications/{notification_id}/read

Convenience: mark a notification read.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
