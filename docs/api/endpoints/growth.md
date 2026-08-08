# Growth

Periodized growth metrics and deterministic forecasts. The *business forecast
engine* that generates forecasts lands in M5 — these endpoints record and read
metric/forecast snapshots. All endpoints are JWT-authenticated. Reads use
`growth_read` (manager+); writes use `growth_manage` (admin/owner only).

## Metrics

## GET /api/v1/growth/metrics

Time series for a metric type. `metric_type` is **required**.

| Query param  | Type     | Notes                            |
| ------------ | -------- | -------------------------------- |
| `metric_type`| string   | Required                         |
| `start`      | datetime | Optional window start (ISO 8601) |
| `end`        | datetime | Optional window end (ISO 8601)   |
| `limit`      | int      | 1–1000, default 500              |

## POST /api/v1/growth/metrics

Record a growth metric. Returns 201.

```json
{"metric_type": "revenue", "period_start": "…", "period_end": "…", "value": "1000"}
```

## GET /api/v1/growth/metrics/types

Distinct metric types recorded for the organization.

## GET /api/v1/growth/metrics/{metric_id}

Fetch a single metric.

## Forecasts

## GET /api/v1/growth/forecasts

List forecasts, optionally filtered by `forecast_type`.

| Query param    | Type   | Notes          |
| -------------- | ------ | -------------- |
| `forecast_type`| string | Optional       |
| `limit`        | int    | 1–500, default 100 |
| `offset`       | int    | Default 0      |

## GET /api/v1/growth/forecasts/latest

Most recent forecast for a `forecast_type` (required). Returns 404 when none
exists.

## POST /api/v1/growth/forecasts

Record a forecast snapshot. Returns 201.

## GET /api/v1/growth/forecasts/{forecast_id}

Fetch a single forecast.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
