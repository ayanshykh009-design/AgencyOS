# Agents

Agent run records and per-agent health/state bookkeeping. The agent *runtime*
that executes agents lands in M4 — these endpoints only persist and read the
data plane. All endpoints are JWT-authenticated. Reads require `agent_read`;
writes/mutations require `agent_manage` (admin/owner only).

## GET /api/v1/agents/states

List per-agent health states, optionally filtered by `status`
(`active`, `paused`, `degraded`, `disabled`).

| Query param | Type   | Notes                          |
| ----------- | ------ | ------------------------------ |
| `status`    | enum   | Optional filter by agent state |
| `limit`     | int    | 1–500, default 100             |

## PATCH /api/v1/agents/states/{agent_name}

Upsert the single health row for `(organization, agent_name)`. The path
`agent_name` must match the body `agent_name`.

| Error          | Meaning                              |
| -------------- | ------------------------------------ |
| `400`          | Path/body agent name mismatch        |

## GET /api/v1/agents/runs

List run records, optionally scoped to an `agent_name` and/or `status`
(`queued`, `running`, `succeeded`, `failed`, `cancelled`). Newest first.

| Query param | Type     | Notes                      |
| ----------- | -------- | -------------------------- |
| `agent_name`| string   | Optional, filter to agent  |
| `status`    | enum     | Optional status filter     |
| `limit`     | int      | 1–500, default 100         |
| `offset`    | int      | Default 0                  |

## POST /api/v1/agents/runs

Persist a new run record (status defaults to `queued`, trigger to `manual`).
Returns 201. No execution occurs here.

```json
{"agent_name": "outreach-agent", "trigger": "manual"}
```

## GET /api/v1/agents/runs/{run_id}

Fetch a single run record.

## PATCH /api/v1/agents/runs/{run_id}

Partial update of run fields (`status`, `output`, `error`,
`duration_ms`, `cost`, `started_at`, `finished_at`).

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
