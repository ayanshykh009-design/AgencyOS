# Batch 3 — Management API (Leads, Assignment, Team, Users, Sources, Research, Founder)

This document covers the Batch 3 endpoints that previously lacked endpoint-level
documentation. All contracts are derived from the running OpenAPI schema and the
endpoint source under the backend endpoint module directory. Every endpoint is
JWT-authenticated (`Authorization: Bearer <token>`), scoped to the authenticated
principal's organization, and uses the standard error envelope
`{error: {code, message, details}}`.

## Leads

### POST /api/v1/leads
Create a lead in the authenticated organization. Requires `lead_write`. Returns 201.

`LeadCreate` requires `organization_id` (UUID, must match the principal) and
accepts optional `first_name`, `last_name`, `company`, `position`, `location`,
`linkedin_url`, `email`, `phone`, `whatsapp`, `website`, `notes` (max 255 where
applicable), `status` (LeadStatus), `score` (0–100), `deal_value` (>= 0),
`lead_source_id`, `owner_user_id`, `stage_id`. Emails are normalized; duplicate
email/phone/website in the org returns `409 lead.duplicate`. Returns `LeadRead`.

### GET /api/v1/leads
Search and filter leads for the org. Requires `lead_read`. Query params: `query`,
`status`, `source_id`, `owner_user_id`, `min_score`, `max_score`, `sort`, `order`,
`limit`, `offset`. Returns a page of `LeadRead`.

### GET /api/v1/leads/funnel
Lead counts by status for the org. Requires `lead_read`. No parameters. Returns
status-bucketed counts. Used by the dashboard.

### GET /api/v1/leads/duplicates
Check for leads matching the supplied contact details. Requires `lead_read`.
Params: `email`, `phone`, `website` (all optional query strings). Returns matches
within the authenticated org only.

### GET /api/v1/leads/{lead_id}
Fetch one lead. Requires `lead_read`. Path: `lead_id` (UUID). Returns `LeadRead`;
`404 lead.not_found` when absent or in another org.

### PATCH /api/v1/leads/{lead_id}
Partial update. Requires `lead_write`. Body `LeadUpdate` (all optional) supports
the editable lead fields including `status`, `score`, stage/owner/source ids,
`close_reason_id` and `deal_value`. Returns `LeadRead`.

### DELETE /api/v1/leads/{lead_id}
Soft-delete a lead. Requires `lead_delete`. Returns 204.
`404 lead.not_found` if absent.

## Lead assignment

### GET /api/v1/assignment/rules
Get the organization's assignment rule. Requires `lead_assign`. Returns
`AssignmentRuleRead` (name, strategy, enabled, target_user_ids, conditions,
last_assigned_index, timestamps).

### PUT /api/v1/assignment/rules
Create or update the assignment rule. Requires `lead_assign`. Body
`AssignmentRuleWrite` requires `name`; optional `strategy` (AssignmentStrategy),
`enabled`, `target_user_ids`, `conditions`. Returns `AssignmentRuleRead`.

### POST /api/v1/assignment/assign-unassigned
Assign every unassigned lead according to the active rule. Requires
`lead_assign`. Returns a summary dict. Organization-scoped.

### POST /api/v1/assignment/leads/{lead_id}/assign
Manually assign (or unassign) a lead. Requires `lead_assign`. Path `lead_id`
(UUID). Body `LeadAssignRequest`: optional `user_id` (UUID or null) and
optional `reason` (<= 255 chars). Returns the updated lead ownership.

### GET /api/v1/assignment/leads/{lead_id}/history
Assignment history for a lead. Requires `lead_assign`. Path `lead_id` (UUID).
Query: `limit`, `offset`. Returns a paginated history. Tenant-scoped.

## Lead sources

### GET /api/v1/lead-sources
List lead sources for the org. Requires authentication. Query
`include_inactive` (bool). Returns a list of `LeadSourceRead`.

### POST /api/v1/lead-sources
Create a lead source. Requires authentication. Body `LeadSourceCreate` requires
`name`; optional `channel` (OutreachChannel), `description`, `is_active`.
Returns 201 `LeadSourceRead`.

### GET /api/v1/lead-sources/{source_id}
Fetch one source. Path `source_id` (UUID). Returns `LeadSourceRead`.

### PATCH /api/v1/lead-sources/{source_id}
Update a source. Body `LeadSourceUpdate` (all optional: `name`, `channel`,
`description`, `is_active`). Returns `LeadSourceRead`.

## Team and users

### POST /api/v1/teams
Invite a team member. Requires `invite_manage`. Body `TeamInviteCreate` requires
`email`; optional `full_name`, `role` (UserRole). Returns 201 `TeamInviteRead`.
No external email is required for the invite to be created.

### GET /api/v1/teams
List team invites for the org. Requires `invite_manage`. Query `limit`, `offset`.
Returns a page of `TeamInviteRead`.

### GET /api/v1/teams/public/{token}
Resolve invite details for the acceptance screen. Public lookup by token;
returns `TeamInviteLookup` (email, role, optional full_name/organization_name).
No organization data beyond the invite is exposed.

### POST /api/v1/teams/accept
Accept an invite and create the account. Body `TeamInviteAccept` requires
`token`, `full_name`, `password`. Returns 200 `AuthResponse` with tokens.

### POST /api/v1/teams/{invite_id}/revoke
Revoke a pending invite. Requires `invite_manage`. Path `invite_id` (UUID).
Returns `TeamInviteRead`.

### GET /api/v1/users
List organization users. Requires `team_manage`. Query `limit`, `offset`.
Returns a page of `UserRead` (no password hashes are exposed).

### POST /api/v1/users
Create a user in the org. Requires `team_manage`. Body `UserCreate` requires
`email`, `full_name`, `organization_id` (must match principal), optional `role`.
Returns 201 `UserRead`.

### GET /api/v1/users/{user_id}
Fetch a user. Requires `team_manage`. Path `user_id` (UUID). Returns `UserRead`.

### PATCH /api/v1/users/{user_id}
Update a user. Requires `team_manage`. Body `UserUpdate` (optional `full_name`,
`role`, `is_active`). Returns `UserRead`.

## Lead research (AI)

### POST /api/v1/research/{lead_id}
Trigger AI research for a lead. Requires `ai_run` (and lead access). Path
`lead_id` (UUID); query `force_refresh` (bool). Returns 202 with the queued
research record. Actual research is worker-owned; no external provider is
contacted synchronously by this endpoint.

### GET /api/v1/research/{lead_id}
Get research for a lead. Requires `lead_read`. Returns `LeadResearchRead`
(status, company_overview, pain_points, tech_stack, recent_news, linkedin_summary,
icp_match_score, raw_data, research_source, timestamps).

### PATCH /api/v1/research/{lead_id}
Manual override of research fields. Requires `lead_write`. Body
`LeadResearchUpdate` (all optional). Returns `LeadResearchRead`.

### DELETE /api/v1/research/{lead_id}
Delete research for a lead (reverts to pending). Requires `lead_write`.
Returns 204.

## Founder conversations

### GET /api/v1/founder/conversations
List founder conversations. Requires `growth_read`. Query `limit`, `offset`,
`include_archived` (bool). Returns a page of `FounderConversationRead`
(id, title, is_archived, created_at, last_message_at).

### GET /api/v1/founder/conversations/{conversation_id}
Get a founder conversation with its messages. Requires `growth_read`. Path
`conversation_id` (UUID). Returns the conversation plus `FounderMessageRead`
items (id, sender, body, sent_at, metadata).

### DELETE /api/v1/founder/conversations/{conversation_id}
Delete a founder conversation. Requires `growth_manage`. Returns 204.

## Notes on tenant isolation
Every endpoint above derives `organization_id` from the authenticated principal
and rejects cross-organization identifiers. Path parameters are validated as
UUIDs (422 on malformed input). No endpoint accepts an arbitrary org id from
the client except where the schema mirrors the principal's org (validated).
