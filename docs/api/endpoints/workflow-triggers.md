# Workflow Triggers

Org-scoped trigger definitions that map workflows to event types or schedules.
All endpoints are JWT-authenticated. Reads require `automation_read`, writes
`automation_write`, deletion `automation_manage`.

## GET /api/v1/workflow-triggers

List triggers. Paginated with `limit` (1–200, default 50) and `offset`.

| Query param  | Type  | Notes                        |
| ------------ | ----- | ---------------------------- |
| `workflow_id` | UUID  | Triggers for one workflow    |
| `enabled`    | bool  | Filter by enabled state      |

Returns a `Page` envelope.

## POST /api/v1/workflow-triggers

Create a trigger. Returns 201.

```json
{
  "organization_id": "…",
  "workflow_id": "…",
  "name": "On lead created",
  "trigger_type": "event",
  "event_type": "lead_created",
  "schedule_cron": null,
  "config": {},
  "enabled": true
}
```

`trigger_type` is `manual`, `event`, or `schedule`.

| Error | Meaning |
| ----- | ------- |
| `400` `trigger.event_type_required` | `event` type without `event_type` |
| `400` `trigger.schedule_cron_required` | `schedule` type without `schedule_cron` |
| `400` `workflow_trigger.organization_required` | Missing `organization_id` (server sets it; defensive) |

## GET /api/v1/workflow-triggers/{trigger_id}

Fetch one trigger.

## PATCH /api/v1/workflow-triggers/{trigger_id}

Partial update (any field optional).

## POST /api/v1/workflow-triggers/{trigger_id}/enable

Set `enabled = true`. A trigger on a `draft` workflow is enabled but inert until
the workflow is activated.

## POST /api/v1/workflow-triggers/{trigger_id}/disable

Set `enabled = false`.

## DELETE /api/v1/workflow-triggers/{trigger_id}

Delete a trigger. Requires `automation_manage`. Returns 204.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
