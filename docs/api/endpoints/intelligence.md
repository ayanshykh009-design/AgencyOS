# Intelligence (Founder Intelligence & Growth Triage — M9)

A triage/orchestration layer over M7/M8 output. The backend reads growth
recommendations, business insights, growth analysis snapshots, and bounded
pipeline condition detectors, then materializes a single, deduplicated,
scored `intelligence_signals` feed. The API only **reads** signals and lets a
founder **acknowledge** or **dismiss** them — it never mutates M7/M8 source
rows. Materialization is owned by the `intelligence_triage_worker` (or the
manual `POST /intelligence/triage/run` trigger).

All endpoints are JWT-authenticated. Reads use `founder_read` (manager+);
acknowledge/dismiss and the manual sweep use `founder_manage`
(admin/owner only).

## GET /api/v1/intelligence/signals

List triaged signals, priority-first. Optional filters:

| Query param     | Type   | Notes                                          |
| --------------- | ------ | ---------------------------------------------- |
| `status`        | enum   | `active`, `acknowledged`, `dismissed`, `superseded` |
| `category`      | enum   | `growth_recommendation`, `business_insight`, `pipeline_risk`, `pipeline_opportunity`, `growth_anomaly`, `founder_briefing` |
| `source_type`   | enum   | `growth_recommendation`, `business_insight`, `growth_analysis`, `pipeline_fact`, `briefing` |
| `limit`         | int    | 1–500, default 50                             |
| `offset`        | int    | Default 0                                      |

Returns a `Page[IntelligenceSignalRead]`.

## GET /api/v1/intelligence/signals/{signal_id}

Fetch a single signal. `404 intelligence_signal.not_found` when absent or not
in the caller's org.

## PATCH /api/v1/intelligence/signals/{signal_id}

Acknowledge or dismiss a signal. The body is `{ "status": "acknowledged" | "dismissed" }`.

| Error                            | Meaning                                                |
| -------------------------------- | ------------------------------------------------------ |
| `422 intelligence_signal.invalid_transition` | Only `acknowledged`/`dismissed` are allowed      |
| `404 intelligence_signal.not_found`          | Signal absent or not in the caller's org         |
| `409 intelligence_signal.superseded`         | Superseded signals are terminal and cannot change |

Same-status transitions are idempotent (return the current row without writing).

## GET /api/v1/intelligence/summary

Roll-up counts over the org's signals: `active`, `acknowledged`, `dismissed`,
`superseded`, `high_priority`, `medium_priority`, `low_priority`, and
`highest_priority_score` (highest active score, or `null`).

## POST /api/v1/intelligence/triage/run

Run a deterministic sweep for the caller's org; the request commits within the
handler. Refuses to run (`503 intelligence_triage.runtime_disabled`) when
`INTELLIGENCE_TRIAGE_ENABLED` is off (fail-closed). Returns counters
(`candidates`, `created`, `updated`, `superseded`, `high_priority`) plus a
deterministic/or-optional-AI `narrative`.

## Determinism & dedup

- `priority_score` is a versioned weighted sum (severity 0.30, business_impact
  0.25, urgency 0.15, confidence 0.10, actionability 0.10, persistence 0.10)
  in `[0, 1]`. Bands: `high ≥ 0.7`, `medium ≥ 0.45`.
- A deterministic `content_hash` (over `source_type`, `source_row_id`, `title`,
  `summary`) makes at most one **live** signal per source. The partial unique
  index `(organization_id, content_hash) WHERE status <> 'superseded'` is the
  invariant; concurrent sweeps retry against the winner's row.
- `business_impact.amount` is carried **only** from values the source actually
  holds — it is never invented.

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
