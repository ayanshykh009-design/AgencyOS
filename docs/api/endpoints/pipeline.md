# Pipeline Management

Kanban pipeline: stages, close reasons, and win/loss bookkeeping. All endpoints
are JWT-authenticated and organization-scoped. Administrative writes (stage and
close-reason mutations) require `pipeline_manage` (admin only); reads and board
queries are available to any authenticated member.

## GET /api/v1/pipeline/stages

List pipeline stages ordered by position, each with a live `lead_count`.

| Status | Meaning                                    |
| ------ | ------------------------------------------ |
| `200`  | `[{ id, name, lifecycle, position, lead_count }, …]` |

## POST /api/v1/pipeline/stages

Create a stage. Requires `pipeline_manage`.

```json
{"name": "Proposal Sent", "lifecycle": "proposal_sent", "position": 4}
```

`lifecycle` is one of `new`, `researching`, `contacted`, `meeting_booked`,
`proposal_sent`, `won`, `lost`. Returns the created stage (201).

| Status | Meaning                                  |
| ------ | ---------------------------------------- |
| `201`  | Stage created                            |
| `400`  | `pipeline.invalid_name` / `pipeline.invalid_lifecycle` |

## PATCH /api/v1/pipeline/stages/{stage_id}

Rename or reorder a stage. Requires `pipeline_manage`. Body fields optional.

```json
{"name": "Meeting Booked", "position": 3}
```

## DELETE /api/v1/pipeline/stages/{stage_id}

Delete a stage; any leads on it move to the default stage first. Requires
`pipeline_manage`. Returns 204.

| Status | Meaning                                        |
| ------ | ---------------------------------------------- |
| `204`  | Stage deleted                                  |
| `404`  | `pipeline.stage_not_found`                     |
| `409`  | `pipeline.default_stage_delete` (last default) |

## POST /api/v1/pipeline/stages/reorder

Persist a full ordering of stage ids. Requires `pipeline_manage`.

```json
{"stage_ids": ["…", "…", "…"]}
```

Returns the updated stage list.

## GET /api/v1/pipeline/close-reasons

List close reasons. Optional `lifecycle` query filters to won/lost reasons.

## POST /api/v1/pipeline/close-reasons

Create a close reason. Requires `pipeline_manage`.

```json
{"name": "Price too high", "lifecycle": "lost"}
```

## DELETE /api/v1/pipeline/close-reasons/{close_reason_id}

Delete a close reason. Requires `pipeline_manage`. Returns 204; blocked with 409
`pipeline.close_reason_in_use` while any lead references it.

## GET /api/v1/pipeline/board

Kanban board: each stage with its lead cards (optionally `limit_per_stage`,
1–200, default 50). Requires no special permission beyond authentication.

## POST /api/v1/pipeline/leads/{lead_id}/stage

Move a lead onto a stage. Moving to a `won`/`lost` stage records the close
(timestamp, optional close reason, deal value bookkeeping); moving off reopens.

```json
{"stage_id": "…", "close_reason_id": "…"}
```

`close_reason_id` is optional and only meaningful for won/lost stages. Returns
the updated `LeadRead`.

| Status | Meaning                              |
| ------ | ------------------------------------ |
| `200`  | Lead moved                           |
| `404`  | `lead.not_found` / `pipeline.stage_not_found` |

## Authentication

All endpoints require `Authorization: Bearer <token>`. Errors use the standard
envelope: `{"error": {"code", "message", "details"?}}`.
