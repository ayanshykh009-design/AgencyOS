# Agents

Agent run records and per-agent health/state bookkeeping. The agent *runtime*
(executor lifecycle + queue draining worker) lands in **M5**: these endpoints
queue and read runs, while status transitions are runtime-owned. All endpoints
are JWT-authenticated. Reads require `agent_read`; writes/mutations require
`agent_manage` (admin/owner only).

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

Queue a new run for an **executable** agent. Returns 201 with the queued run;
no execution occurs here (the runtime worker drains the queue when
`AGENT_RUNTIME_ENABLED` is on). Initial status must be `queued` (default);
status transitions are runtime-owned. Rate-limited.

```json
{"agent_name": "founder_assistant", "input": {"goal": "summarize this week"}, "idempotency_key": "sum-2026-08-10"}
```

| Field            | Type   | Notes                                        |
| ---------------- | ------ | -------------------------------------------- |
| `agent_name`     | string | One of the executable agents                 |
| `trigger`        | enum   | `manual` (default), `schedule`, `workflow`   |
| `workflow_id`    | uuid   | Optional source workflow                     |
| `input`          | object | Run input (e.g. `{"goal": "..."}`)           |
| `idempotency_key`| string | Optional; replays return the existing run    |

| Error                         | Meaning                                   |
| ----------------------------- | ----------------------------------------- |
| `404 agent.unknown`           | Agent does not exist                      |
| `409 agent.not_executable`    | Agent is registered-only / not executable |
| `400 agent_run.invalid_initial_status` | Status was not `queued`          |
| `409 agent_run.duplicate_idempotency_key` | Idempotency key collision (retry-safe) |

## GET /api/v1/agents/runs/{run_id}

Fetch a single run record.

## POST /api/v1/agents/runs/{run_id}/cancel

Cancel a run. `queued` runs transition to `cancelled` immediately; a `running`
run is flagged (`cancel_requested_at`) and the worker lands it on `cancelled`
when the executor returns. Already-cancelled runs are idempotent; terminal
runs return `409 agent_run.not_cancellable`. Rate-limited.

## PATCH /api/v1/agents/runs/{run_id}

Partial update of run **metadata only** — `output`, `error`, `duration_ms`,
`cost`, `started_at`, `finished_at`. There is no `status` field: every status
transition is owned by the runtime (worker) and its guarded state machine.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
