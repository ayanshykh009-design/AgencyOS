# RLS Policies

Row Level Security policies for the Supabase-managed environment, one SQL file
per table. `_helpers.sql` defines `public.tenant_org_id()`, which resolves the
caller's organization from `auth.uid()`.

- `_helpers.sql` — shared tenant-resolution helper.
- One policy file per table: `organizations`, `users`, `lead_sources`,
  `leads`, `lead_research`, `outreach_messages`, `outreach_attempts`,
  `follow_ups`, `manual_outreach_queue`, `conversations`,
  `conversation_messages`, `activity_logs`, `import_jobs`,
  `import_row_errors`, `provider_usage`.

Every policy scopes access by `organization_id = public.tenant_org_id()`.
Append-only tables (`conversation_messages`, `activity_logs`,
`import_row_errors`) expose only `SELECT` and `INSERT`. The `anon` /
`authenticated` roles and `auth.uid()` are provided by Supabase.

RLS is enabled by each table's migration; these files only add the policies.
The backend `service_role` path bypasses RLS where the API must act across
tenants (kept minimal per the AGENTS.md golden rules).
