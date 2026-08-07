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
and whose workflow is `active`, queueing one execution per matching trigger.
`consumed` in the response reflects the fan-out result. Event reads never block;
consumption is recorded on the event row.

| Error | Meaning |
| ----- | ------- |
| `400` `event.organization_required` | Missing `organization_id` (server sets it; defensive) |
| `400` `event.payload_too_large` | Payload exceeds `EVENT_MAX_PAYLOAD_BYTES` |
| `409` `automation.paused.queue_blocked` | Automation is paused (kill switch) — no event row is written and nothing is queued |

### Production guards

- **Payload size:** a payload whose serialized size exceeds
  `EVENT_MAX_PAYLOAD_BYTES` (default 262144) is rejected with `400
  event.payload_too_large` before any DB write. The payload is copied into
  every queued execution's input, so this caps per-event write amplification.
- **Fan-out bound:** at most `EVENT_FANOUT_MAX_TRIGGERS` (default 100)
  executions are queued per event. A trigger set larger than the limit is
  truncated (oldest-created first); the publish still succeeds and the event is
  marked consumed. Truncation increments the `event_fanout_truncated` counter
  and logs a warning — a persistent non-zero value means an event_type matches
  far more triggers than intended.

## GET /api/v1/workflow-events

List events, newest first. Paginated with `limit` (1–200, default 50) and
`offset`.

| Query param  | Type  | Notes                     |
| ------------ | ----- | ------------------------- |
| `event_type` | str   | Filter by event name      |
| `consumed`   | bool  | Filter by consumption     |

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
