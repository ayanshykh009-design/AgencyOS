# Approvals

Gated approval requests and the immutable audit log. The approval *flow* that
gates workflow execution is the API surface here; gating workers land in M6.
All endpoints are JWT-authenticated. Reads require `approval_read`; create and
decide require `approval_manage` (manager+).

## GET /api/v1/approvals

List approval requests, optionally filtered by `status`
(`pending`, `approved`, `denied`, `expired`, `cancelled`).

| Query param | Type | Notes          |
| ----------- | ---- | -------------- |
| `status`    | enum | Optional       |
| `limit`     | int  | 1–500, default 100 |
| `offset`    | int  | Default 0      |

## POST /api/v1/approvals

Create an approval request. Returns 201. The creator becomes
`requested_by_user_id`; each request auto-appends a `requested` audit log
entry. Defaults `expires_at` to `now() + APPROVAL_EXPIRY_HOURS` (24h).

```json
{"title": "Ship Q3 report", "approver_user_id": "…"}
```

## GET /api/v1/approvals/pending-count

Open (pending) approval request count for the organization.

## GET /api/v1/approvals/{request_id}

Fetch a single approval request.

## POST /api/v1/approvals/{request_id}/decision

Approve or deny a pending request. Transitions to `approved`/`denied`, stamps
`decided_by_user_id` (defaults to the actor), and appends an `approved`/
`denied` audit log entry. Fails with 409 if the request is no longer pending.

```json
{"approve": true, "decision_note": "Looks good"}
```

## GET /api/v1/approvals/{request_id}/logs

Audit timeline for a request (oldest first).

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
