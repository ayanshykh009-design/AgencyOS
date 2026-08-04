# Workflow Events

Org-scoped domain events that drive event-triggered workflows. All endpoints are
JWT-authenticated. Reads require `automation_read`, publishing `automation_write`.

## POST /api/v1/workflow-events

Publish an event that can trigger workflows. Returns 201 with `{event_id,
consumed}`.

```json
{
  "organization_id": "…",
  "event_type": "lead_created",
  "payload": { "lead_id": "…", "source": "form" }
}
```

Publishing fans out to every enabled `event` trigger whose `event_type` matches
and whose workflow is `active`, queuing one execution per matching trigger.
`consumed` in the response reflects the fan-out result. Event reads never block;
consumption is recorded on the event row.

## GET /api/v1/workflow-events

List events, newest first. Paginated with `limit` (1–200, default 50) and
`offset`.

| Query param  | Type  | Notes                     |
| ------------ | ----- | ------------------------- |
| `event_type` | str   | Filter by event name      |
| `consumed`   | bool  | Filter by consumption     |

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
