# Communications

Founder communications summary — a read-only aggregate digest over the Phase 5D
inbox surfaces (notifications, approvals, briefings, insights). The full
delivery layer lands in M6; this is the summary read surface only. All endpoints
are JWT-authenticated and require the conjunction of `notification_read`,
`growth_read`, and `approval_read` (i.e. manager+), since the digest includes
manager-level insight counts.

## GET /api/v1/communications/summary

Single-view digest for the current user:

| Field                 | Type                | Notes                                  |
| --------------------- | ------------------- | -------------------------------------- |
| `unread_notifications`| int                 | Current user's unread inbox count      |
| `pending_approvals`   | int                 | Organization's open approval count     |
| `active_insights`     | int                 | Organization's active insight count    |
| `latest_briefing`     | BriefingRead \| null| Most recent daily briefing, if any    |

## Authentication

`Authorization: Bearer <token>`. Errors use the standard envelope.
