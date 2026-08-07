# Automation Control (Kill Switch)

Global operator controls for the automation engine: read the automation
status and pause/resume **all** execution, queueing, and schedule dispatch
instance-wide. All endpoints are JWT-authenticated and **admin-only**
(`automation_control` per the RBAC matrix — `owner`/`admin`).

The kill switch is a single global flag backed by the `system_settings` table
(`automation.enabled` + pause metadata). It is not per-organization: pausing
stops every tenant's automation until an operator resumes.

## GET /api/v1/automation/status

Return the current automation status and pause metadata.

```json
{
  "enabled": false,
  "paused_by": "00000000-0000-0000-0000-000000000201",
  "paused_at": "2026-08-05T14:22:10+00:00",
  "paused_reason": "Deploy freeze — n8n maintenance"
}
```

| Field          | Type     | Meaning                                   |
| -------------- | -------- | ----------------------------------------- |
| `enabled`      | bool     | `false` while automation is paused        |
| `paused_by`    | uuid?    | User id of the operator who paused        |
| `paused_at`    | datetime?| ISO-8601 UTC timestamp of the pause       |
| `paused_reason`| str?     | Operator-supplied pause reason            |

When the flag has never been set the response is `{"enabled": true}` with the
pause fields `null` (enabled is the default).

## POST /api/v1/automation/pause

Pause all automation. Body:

```json
{ "reason": "Deploy freeze — n8n maintenance" }
```

Returns the same status payload as `GET /status`. Writes an `activity_logs`
entry with `automation_paused` (actor, before/after, and reason in `metadata`).

| Error | Meaning                                   |
| ----- | ----------------------------------------- |
| `409` `automation.already_paused` | Automation is already paused |
| `422` (Pydantic) | Empty/too-long `reason` |

## POST /api/v1/automation/resume

Resume automation after a pause. Body is optional/empty. Returns the status
payload and writes an `activity_logs` entry with `automation_resumed`.

| Error | Meaning                                   |
| ----- | ----------------------------------------- |
| `409` `automation.already_resumed` | Automation is already running |

## Effect of a pause

While `enabled=false`, every automation entry point is blocked:

| Entry point                              | Behavior when paused                              |
| ---------------------------------------- | ------------------------------------------------- |
| `POST /workflow-executions` (run-now)    | `409 automation.paused.queue_blocked`             |
| `POST /workflow-executions/{id}/retry`   | `409 automation.paused`                           |
| `POST /workflow-events` (publish)        | `409 automation.paused.queue_blocked`             |
| Execution worker (retry + queue sweep)   | Phases skipped; heartbeats and stale-timeout housekeeping continue |
| Schedule dispatcher sweep                | No-op (ticks left for the next sweep after resume) |

Blocked responses include the pause reason in the message envelope. In-flight
`running` executions are **not** interrupted; they finish, time out, or are
cancelled normally. Queued work is preserved and drains once automation
resumes.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
