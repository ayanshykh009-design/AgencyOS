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

## Analyses (M7)

## GET /api/v1/growth/analyses

List deterministic analysis snapshots, newest first.

| Query param    | Type     | Notes                                              |
| -------------- | -------- | -------------------------------------------------- |
| `analysis_type`| enum     | `health`, `kpis`, `pipeline`, `funnel`, `conversion`, `revenue`, `activity`, `bottlenecks`, `opportunities`, `trends` |
| `status`       | enum     | `completed`, `failed`                              |
| `start`/`end`  | datetime | Optional window filter                             |
| `limit`        | int      | 1–500, default 100                                 |
| `offset`       | int      | Default 0                                          |

## POST /api/v1/growth/analyses/run

Run one deterministic engine over a window and persist a snapshot. Returns 201.
`period_start`/`period_end` are required ISO datetimes; `generated_by` defaults
to `user`. Failed runs are stored with `status=failed` and the error message.

```json
{"analysis_type": "kpis", "period_start": "…", "period_end": "…", "generated_by": "user"}
```

## POST /api/v1/growth/analyses/run-all

Run every engine over the window, persisting one snapshot per type plus
evidence-backed recommendations in a single transaction. Returns 201 with a
list of analysis snapshots.

## GET /api/v1/growth/analyses/{analysis_id}

Fetch a single analysis snapshot.

## Recommendations (M7)

## GET /api/v1/growth/recommendations

List evidence-backed recommendations. `status` (`active`, `acknowledged`,
`applied`, `dismissed`) and `priority` (`high`, `medium`, `low`) are optional
filters.

## GET /api/v1/growth/recommendations/counts

Per-triage-status counts: `{active, acknowledged, applied, dismissed}`.

## PATCH /api/v1/growth/recommendations/{recommendation_id}

Triage a recommendation: update `status` and/or `priority`.

```json
{"status": "applied", "priority": "medium"}
```

## Scenarios (M7)

## GET /api/v1/growth/scenarios

List saved what-if scenarios. `forecast_id` optionally filters by source
forecast.

## POST /api/v1/growth/scenarios

Evaluate and save a what-if scenario. Returns 201. `period_start`/`period_end`
default to the last 30 days. Deltas are multipliers (`1.0` = no change).

```json
{"name": "Double leads", "assumption_deltas": {"new_leads_delta": 2.0}, "period_start": "…", "period_end": "…"}
```

## GET /api/v1/growth/scenarios/{scenario_id}

Fetch a single saved scenario.

## DELETE /api/v1/growth/scenarios/{scenario_id}

Delete a saved scenario. Returns 204.

## Health weights (M7)

## GET /api/v1/growth/health-weights

Active weight set, or the defaults with `is_default: true` when none has been
saved. Weights sum to 1 across `pipeline_health`, `activity_level`,
`conversion_health`, `revenue_health`, `coverage_health`.

## POST /api/v1/growth/health-weights

Save a new active weight-set version (bumps `version`, deactivates the old
row). Returns 201.

```json
{"weights": {"pipeline_health": 0.3, "activity_level": 0.2}}
```

## Forecast generation (M7)

## POST /api/v1/growth/forecasts/run

Generate and persist a deterministic forecast. Returns 201.

| Field           | Type     | Notes                                             |
| --------------- | -------- | ------------------------------------------------- |
| `method`        | enum     | `linear_trend` (default), `moving_average`, `pipeline_weighted`, `seasonal_naive` |
| `period_start`  | datetime | Required base window start                        |
| `period_end`    | datetime | Required base window end                          |
| `horizon_start` | datetime | Required projection start                         |
| `horizon_end`   | datetime | Required projection end                           |
| `forecast_type` | string   | Default `revenue`                                 |

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
