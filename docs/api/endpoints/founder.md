# Founder

Generated founder briefings and business insights. *Generation* of these
artifacts is driven by the M7 growth agent; these endpoints curate/read them and
triage insight status. All endpoints are JWT-authenticated. Reads and triage
use `growth_read` (manager+); create/update/delete use `growth_manage`
(admin/owner only).

## Briefings

## GET /api/v1/founder/briefings

List briefings, optionally filtered by `briefing_type`
(`daily`, `weekly`, `manual`). Newest first.

## GET /api/v1/founder/briefings/latest

Most recent briefing of a given cadence (default `daily`). Returns 404 when none
exists.

## POST /api/v1/founder/briefings

Create a briefing. Returns 201.

## GET /api/v1/founder/briefings/{briefing_id}

Fetch a single briefing.

## Insights

## GET /api/v1/founder/insights

List business insights, optionally filtered by `status`
(`active`, `acknowledged`, `dismissed`) and `severity`
(`info`, `low`, `medium`, `high`, `critical`).

| Query param | Type   | Notes          |
| ----------- | ------ | -------------- |
| `status`    | enum   | Optional       |
| `severity`  | enum   | Optional       |
| `limit`     | int    | 1–500, default 100 |
| `offset`    | int    | Default 0      |

## GET /api/v1/founder/insights/counts

Active insight count plus counts grouped by `insight_type`.

## POST /api/v1/founder/insights

Create a business insight. Returns 201.

## GET /api/v1/founder/insights/{insight_id}

Fetch a single insight.

## PATCH /api/v1/founder/insights/{insight_id}

Triage an insight (`status` and/or `severity`).

## DELETE /api/v1/founder/insights/{insight_id}

Delete an insight. Returns 204.

## Founder assistant (Batch 5)

These routes use `FOUNDER_READ` for reads and `FOUNDER_MANAGE` for messages,
deletes, and proposal decisions.

### POST /api/v1/founder/chat

Sends a grounded message to the single Founder Assistant. Requires
`FOUNDER_MANAGE`. Uses the shared AI request limiter (`RATE_LIMIT_AI`); excess
traffic receives `429` with `Retry-After` and `X-RateLimit-*` headers. Provider
failures are returned as stable generic error codes; raw provider URLs, bodies,
and credentials are never included in the response.

### GET /api/v1/founder/conversations

Lists conversations with `limit`, `offset`, and `include_archived`. `total` is
the true filtered count, not the page length. Requires `FOUNDER_READ`.

### GET /api/v1/founder/conversations/{conversation_id}

Returns one conversation and its messages. Requires `FOUNDER_READ`.

### DELETE /api/v1/founder/conversations/{conversation_id}

Deletes a conversation. Requires `FOUNDER_MANAGE`; returns `204`.

### GET /api/v1/founder/proposals

Lists action proposals. The status filter is `proposal_status` (including
`cancelled` and `executing`); `total` is the true filtered count. Requires
`FOUNDER_READ`.

### POST /api/v1/founder/proposals/{proposal_id}/decide

Approves or denies a proposal. Requires `FOUNDER_MANAGE`. Decisions are claimed
atomically: only one concurrent decision can win, and only the winning approval
executes a side effect.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
