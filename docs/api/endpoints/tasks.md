# Tasks

Org-scoped to-dos linked to leads, with assignees, due/reminder times,
priorities, and recurrence. All endpoints are JWT-authenticated. Reads require
`task_read`, writes `task_write`, deletion `task_manage` (per the RBAC matrix).

## GET /api/v1/tasks

List tasks with filters. Sortable (`due_at`, `created_at`, `priority`, `title`)
in `asc`/`desc` order; paginated with `limit` (1–200, default 50) and `offset`.

| Query param      | Type    | Notes                          |
| ---------------- | ------- | ------------------------------ |
| `lead_id`        | UUID    | Tasks for one lead             |
| `assignee_user_id` | UUID  | Tasks assigned to one user     |
| `status`         | enum    | `todo`, `in_progress`, `completed`, `cancelled` |
| `priority`       | enum    | `low`, `medium`, `high`, `urgent` |
| `due_before`     | datetime | Inclusive upper bound          |
| `due_after`      | datetime | Inclusive lower bound          |

Returns a `Page` envelope: `{items, total, limit, offset}`.

## POST /api/v1/tasks

Create a task. Returns 201.

```json
{
  "title": "Follow up on proposal",
  "description": "Ask about the revised scope",
  "lead_id": "…",
  "assignee_user_id": "…",
  "due_at": "2026-08-05T09:00:00Z",
  "priority": "high",
  "recurrence_frequency": "weekly",
  "recurrence_interval": 1
}
```

| Error | Meaning                                           |
| ----- | ------------------------------------------------- |
| `400` `task.title_required` | Blank title                        |
| `400` `task.reminder_after_due` | Reminder later than due        |
| `400` `task.recurrence_requires_frequency` | Interval without frequency |
| `400` `task.invalid_assignee` | Inactive/unknown assignee         |
| `404` `task.not_found` / lead missing               |

Recurrence: `recurrence_frequency` (`daily`, `weekly`, `monthly`) paired with
`recurrence_interval` (>= 1). Monthly dates clamp to the last valid day
(e.g. Jan 31 → Feb 28). Emits a `task_created` activity entry.

## GET /api/v1/tasks/reminders/due

Sweep for open tasks whose `reminder_at` has passed, newest first. Used by
notification workers and the UI badge.

## GET /api/v1/tasks/{task_id}

Fetch one task.

## PATCH /api/v1/tasks/{task_id}

Partial update (any field optional). Setting `status` to `completed` routes
through completion: one-off tasks finish; recurring tasks advance their next
due/reminder dates and stay `todo`. Reopening a completed task clears
`completed_at`.

## POST /api/v1/tasks/{task_id}/complete

Mark a task complete (idempotent). Emits `task_completed` and, for recurring
tasks, schedules the next occurrence in the response metadata
(`{"recurred": true}`).

## DELETE /api/v1/tasks/{task_id}

Delete a task. Requires `task_manage`. Returns 204.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
