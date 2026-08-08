# Founder

Generated founder briefings and business insights. *Generation* of these
artifacts lands in M7 (growth agent); these endpoints curate/read them and
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

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
