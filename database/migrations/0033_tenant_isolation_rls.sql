-- Backend tenant isolation: RLS roles, per-org policies, and privilege grants.
--
-- Why this exists
-- ---------------
-- Before this migration the numbered migrations only ENABLED Row Level
-- Security and shipped the actual `CREATE POLICY` statements in the
-- Supabase-only directory `database/supabase/policies/`, which the canonical
-- runner (`scripts/db/migrate.sh`) never applies. Plain-PostgreSQL deployments
-- and the CI service therefore ran with RLS enabled but NOT restricted: every
-- connection resolved as the table owner, and table owners bypass RLS unless
-- FORCE ROW LEVEL SECURITY is set. Tenant isolation was a load-bearing myth.
--
-- This migration closes the gap for the backend's own data plane:
--
--   * two dedicated application roles:
--       - `agencyos_app`    — subject to the per-organization policies
--                             (used by the API/data plane for user-scoped work)
--       - `agencyos_worker` — BYPASSRLS (used by the cross-tenant workers, the
--                             health sweep, and retention data cleanup)
--   * `public.tenant_org_id()` — SECURITY DEFINER, resolves the caller's
--     organization from the `app.current_organization_id` GUC first (set by
--     the backend request context) and falls back to `auth.uid()` only when a
--     Supabase `auth` schema is present. SECURITY DEFINER prevents the policy
--     recursion that plagues `users` self-referencing queries.
--   * seven SECURITY DEFINER auth lookups the API must run BEFORE any identity /
--     org is established (login, refresh, register slug check, webhook
--     org-by-slug, unauthenticated invite token): they resolve by
--     id/email/slug/token across the whole cluster, which RLS must not hide.
--     EXECUTE is revoked from PUBLIC and granted only to `agencyos_app`
--     (and `agencyos_worker` where relevant).
--   * per-organization SELECT/INSERT/UPDATE/DELETE policies pinned to
--     `organization_id = tenant_org_id()` on every tenant table, plus
--     `organizations` scoped by `id`. The instance-global tables
--     (`system_settings`, `credential_key_versions`) are whitelisted with
--     `USING (true)` — they carry no tenant data and are gated by API RBAC.
--     `worker_health` is SELECT-only for `agencyos_app` (workers write it
--     through the BYPASSRLS role).
--
-- Replay safety: role creation is guarded (PostgreSQL has no CREATE ROLE IF
-- NOT EXISTS), every policy is `DROP POLICY IF EXISTS` + `CREATE`, and GRANTs
-- are idempotent. `ALTER ROLE ... BYPASSRLS` / the role guards require the
-- migration runner to be a superuser (CI and the canonical runner qualify).
--
-- NOTE on ownership: the API only becomes RLS-restricted when its connection
-- role is subject to these policies (not the table owner / superuser). The
-- production DATABASE_URL must resolve to a role that lands in `agencyos_app`
-- (login role with membership, or SET ROLE at connection start); the workers
-- use WORKER_DATABASE_URL, which must resolve to `agencyos_worker`.
-- FORCE ROW LEVEL SECURITY is intentionally NOT applied so developer/CI
-- owner connections keep working unchanged; production applies the app role.

-- =====================================================================
-- 1. Application roles (cluster-global, guarded)
-- =====================================================================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'agencyos_app') THEN
    CREATE ROLE agencyos_app NOLOGIN;
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'agencyos_worker') THEN
    CREATE ROLE agencyos_worker NOLOGIN BYPASSRLS;
  END IF;
  -- Converge an accidentally pre-created non-bypassing role (idempotent).
  -- Requires superuser; fails loudly otherwise (operator must not skip this).
  ALTER ROLE agencyos_worker NOLOGIN BYPASSRLS;
END
$$;

-- =====================================================================
-- 2. Tenant resolver (SECURITY DEFINER; GUC-first, auth fallback)
-- =====================================================================
CREATE OR REPLACE FUNCTION public.tenant_org_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  org_setting text;
BEGIN
  -- GUC-first: set by the backend request context for every user-scoped
  -- transaction (defeats pooled-connection leakage via re-set at txn begin).
  org_setting := NULLIF(current_setting('app.current_organization_id', true), '');
  IF org_setting IS NOT NULL THEN
    BEGIN
      RETURN org_setting::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
      RETURN NULL;
    END;
  END IF;

  -- Supabase fallback: only valid where the managed `auth` schema exists and
  -- provides auth.uid(). Absent (plain PostgreSQL) it stays NULL.
  IF to_regnamespace('auth') IS NOT NULL AND to_regprocedure('auth.uid()') IS NOT NULL THEN
    RETURN (
      SELECT u.organization_id
      FROM public.users u
      WHERE u.id = auth.uid() AND u.is_active
      LIMIT 1
    );
  END IF;

  RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION public.tenant_org_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.tenant_org_id() TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.tenant_org_id() TO agencyos_worker;

-- Supabase/PostgREST compatibility: the managed policy files under
-- database/supabase/policies (applied in the Supabase environment and by the
-- RLS integration tests) call tenant_org_id() as `anon`/`authenticated`.
-- The REVOKE above would otherwise break them (CREATE OR REPLACE preserves
-- ACLs, so the revoke sticks across helper re-creations). Those roles do not
-- exist on a plain PostgreSQL deployment, so grant conditionally.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'anon') THEN
    GRANT EXECUTE ON FUNCTION public.tenant_org_id() TO anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'authenticated') THEN
    GRANT EXECUTE ON FUNCTION public.tenant_org_id() TO authenticated;
  END IF;
END
$$;

-- =====================================================================
-- 3. Auth lookups that must run before identity is established
--    (SECURITY DEFINER so RLS cannot hide cross-tenant rows from them).
-- =====================================================================
CREATE OR REPLACE FUNCTION public.app_get_user_by_id(p_user_id uuid)
RETURNS SETOF public.users
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT * FROM public.users WHERE id = p_user_id;
$$;

CREATE OR REPLACE FUNCTION public.app_get_user_by_email(p_email text)
RETURNS SETOF public.users
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT * FROM public.users WHERE email = lower(ltrim(btrim(p_email)));
$$;

CREATE OR REPLACE FUNCTION public.app_find_active_user_by_email(p_email text)
RETURNS SETOF public.users
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT * FROM public.users
  WHERE email = lower(ltrim(btrim(p_email))) AND is_active;
$$;

CREATE OR REPLACE FUNCTION public.app_get_valid_refresh_token(
  p_token_hash text,
  p_now timestamptz
)
RETURNS SETOF public.refresh_tokens
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT * FROM public.refresh_tokens
  WHERE token_hash = p_token_hash
    AND revoked_at IS NULL
    AND expires_at > p_now;
$$;

CREATE OR REPLACE FUNCTION public.app_get_organization_by_slug(p_slug text)
RETURNS SETOF public.organizations
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT * FROM public.organizations WHERE slug = p_slug;
$$;

CREATE OR REPLACE FUNCTION public.app_slug_available(p_slug text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT NOT EXISTS (SELECT 1 FROM public.organizations WHERE slug = p_slug);
$$;

-- Unauthenticated invite lookup (POST /teams/public/{token}, POST /teams/accept):
-- the invitee has no session and no org context yet, but the token digest is
-- unguessable and single-purpose, so resolving it across tenants is required
-- for the acceptance flow. The caller activates the invite's organization
-- immediately after this lookup.
CREATE OR REPLACE FUNCTION public.app_get_team_invite_by_token_hash(p_token_hash text)
RETURNS SETOF public.team_invites
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT * FROM public.team_invites WHERE token_hash = p_token_hash;
$$;

REVOKE ALL ON FUNCTION public.app_get_user_by_id(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_get_user_by_email(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_find_active_user_by_email(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_get_valid_refresh_token(text, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_get_organization_by_slug(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_slug_available(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_get_team_invite_by_token_hash(text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.app_get_user_by_id(uuid) TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.app_get_user_by_email(text) TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.app_find_active_user_by_email(text) TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.app_get_valid_refresh_token(text, timestamptz) TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.app_get_organization_by_slug(text) TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.app_slug_available(text) TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.app_get_team_invite_by_token_hash(text) TO agencyos_app;

GRANT EXECUTE ON FUNCTION public.app_get_user_by_id(uuid) TO agencyos_worker;
GRANT EXECUTE ON FUNCTION public.app_get_user_by_email(text) TO agencyos_worker;
GRANT EXECUTE ON FUNCTION public.app_find_active_user_by_email(text) TO agencyos_worker;
GRANT EXECUTE ON FUNCTION public.app_get_valid_refresh_token(text, timestamptz) TO agencyos_worker;
GRANT EXECUTE ON FUNCTION public.app_get_organization_by_slug(text) TO agencyos_worker;
GRANT EXECUTE ON FUNCTION public.app_slug_available(text) TO agencyos_worker;
GRANT EXECUTE ON FUNCTION public.app_get_team_invite_by_token_hash(text) TO agencyos_worker;

-- =====================================================================
-- 4. Per-organization policies on every tenant table.
--    Pattern: SELECT / INSERT / UPDATE / DELETE pinned to
--    organization_id = public.tenant_org_id().
-- =====================================================================

-- --- organizations (scoped by primary key) ----------------------------
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS organizations_select_tenant ON public.organizations;
CREATE POLICY organizations_select_tenant ON public.organizations
  FOR SELECT TO agencyos_app
  USING (id = public.tenant_org_id());
DROP POLICY IF EXISTS organizations_insert_tenant ON public.organizations;
CREATE POLICY organizations_insert_tenant ON public.organizations
  FOR INSERT TO agencyos_app
  WITH CHECK (id = public.tenant_org_id());
DROP POLICY IF EXISTS organizations_update_tenant ON public.organizations;
CREATE POLICY organizations_update_tenant ON public.organizations
  FOR UPDATE TO agencyos_app
  USING (id = public.tenant_org_id())
  WITH CHECK (id = public.tenant_org_id());
DROP POLICY IF EXISTS organizations_delete_tenant ON public.organizations;
CREATE POLICY organizations_delete_tenant ON public.organizations
  FOR DELETE TO agencyos_app
  USING (id = public.tenant_org_id());

-- --- users ------------------------------------------------------------
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS users_select_tenant ON public.users;
CREATE POLICY users_select_tenant ON public.users
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS users_insert_tenant ON public.users;
CREATE POLICY users_insert_tenant ON public.users
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS users_update_tenant ON public.users;
CREATE POLICY users_update_tenant ON public.users
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS users_delete_tenant ON public.users;
CREATE POLICY users_delete_tenant ON public.users
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- lead_sources -----------------------------------------------------
ALTER TABLE public.lead_sources ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lead_sources_select_tenant ON public.lead_sources;
CREATE POLICY lead_sources_select_tenant ON public.lead_sources
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_sources_insert_tenant ON public.lead_sources;
CREATE POLICY lead_sources_insert_tenant ON public.lead_sources
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_sources_update_tenant ON public.lead_sources;
CREATE POLICY lead_sources_update_tenant ON public.lead_sources
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_sources_delete_tenant ON public.lead_sources;
CREATE POLICY lead_sources_delete_tenant ON public.lead_sources
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- leads ------------------------------------------------------------
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS leads_select_tenant ON public.leads;
CREATE POLICY leads_select_tenant ON public.leads
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS leads_insert_tenant ON public.leads;
CREATE POLICY leads_insert_tenant ON public.leads
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS leads_update_tenant ON public.leads;
CREATE POLICY leads_update_tenant ON public.leads
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS leads_delete_tenant ON public.leads;
CREATE POLICY leads_delete_tenant ON public.leads
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- lead_research ----------------------------------------------------
ALTER TABLE public.lead_research ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lead_research_select_tenant ON public.lead_research;
CREATE POLICY lead_research_select_tenant ON public.lead_research
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_research_insert_tenant ON public.lead_research;
CREATE POLICY lead_research_insert_tenant ON public.lead_research
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_research_update_tenant ON public.lead_research;
CREATE POLICY lead_research_update_tenant ON public.lead_research
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_research_delete_tenant ON public.lead_research;
CREATE POLICY lead_research_delete_tenant ON public.lead_research
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- outreach_messages ------------------------------------------------
ALTER TABLE public.outreach_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outreach_messages_select_tenant ON public.outreach_messages;
CREATE POLICY outreach_messages_select_tenant ON public.outreach_messages
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS outreach_messages_insert_tenant ON public.outreach_messages;
CREATE POLICY outreach_messages_insert_tenant ON public.outreach_messages
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS outreach_messages_update_tenant ON public.outreach_messages;
CREATE POLICY outreach_messages_update_tenant ON public.outreach_messages
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS outreach_messages_delete_tenant ON public.outreach_messages;
CREATE POLICY outreach_messages_delete_tenant ON public.outreach_messages
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- outreach_attempts ------------------------------------------------
ALTER TABLE public.outreach_attempts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outreach_attempts_select_tenant ON public.outreach_attempts;
CREATE POLICY outreach_attempts_select_tenant ON public.outreach_attempts
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS outreach_attempts_insert_tenant ON public.outreach_attempts;
CREATE POLICY outreach_attempts_insert_tenant ON public.outreach_attempts
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS outreach_attempts_update_tenant ON public.outreach_attempts;
CREATE POLICY outreach_attempts_update_tenant ON public.outreach_attempts
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS outreach_attempts_delete_tenant ON public.outreach_attempts;
CREATE POLICY outreach_attempts_delete_tenant ON public.outreach_attempts
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- follow_ups -------------------------------------------------------
ALTER TABLE public.follow_ups ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS follow_ups_select_tenant ON public.follow_ups;
CREATE POLICY follow_ups_select_tenant ON public.follow_ups
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS follow_ups_insert_tenant ON public.follow_ups;
CREATE POLICY follow_ups_insert_tenant ON public.follow_ups
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS follow_ups_update_tenant ON public.follow_ups;
CREATE POLICY follow_ups_update_tenant ON public.follow_ups
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS follow_ups_delete_tenant ON public.follow_ups;
CREATE POLICY follow_ups_delete_tenant ON public.follow_ups
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- manual_outreach_queue --------------------------------------------
ALTER TABLE public.manual_outreach_queue ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS manual_outreach_queue_select_tenant ON public.manual_outreach_queue;
CREATE POLICY manual_outreach_queue_select_tenant ON public.manual_outreach_queue
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS manual_outreach_queue_insert_tenant ON public.manual_outreach_queue;
CREATE POLICY manual_outreach_queue_insert_tenant ON public.manual_outreach_queue
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS manual_outreach_queue_update_tenant ON public.manual_outreach_queue;
CREATE POLICY manual_outreach_queue_update_tenant ON public.manual_outreach_queue
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS manual_outreach_queue_delete_tenant ON public.manual_outreach_queue;
CREATE POLICY manual_outreach_queue_delete_tenant ON public.manual_outreach_queue
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- conversations ----------------------------------------------------
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversations_select_tenant ON public.conversations;
CREATE POLICY conversations_select_tenant ON public.conversations
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS conversations_insert_tenant ON public.conversations;
CREATE POLICY conversations_insert_tenant ON public.conversations
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS conversations_update_tenant ON public.conversations;
CREATE POLICY conversations_update_tenant ON public.conversations
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS conversations_delete_tenant ON public.conversations;
CREATE POLICY conversations_delete_tenant ON public.conversations
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- conversation_messages --------------------------------------------
ALTER TABLE public.conversation_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversation_messages_select_tenant ON public.conversation_messages;
CREATE POLICY conversation_messages_select_tenant ON public.conversation_messages
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS conversation_messages_insert_tenant ON public.conversation_messages;
CREATE POLICY conversation_messages_insert_tenant ON public.conversation_messages
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS conversation_messages_update_tenant ON public.conversation_messages;
CREATE POLICY conversation_messages_update_tenant ON public.conversation_messages
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS conversation_messages_delete_tenant ON public.conversation_messages;
CREATE POLICY conversation_messages_delete_tenant ON public.conversation_messages
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- activity_logs ----------------------------------------------------
ALTER TABLE public.activity_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS activity_logs_select_tenant ON public.activity_logs;
CREATE POLICY activity_logs_select_tenant ON public.activity_logs
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS activity_logs_insert_tenant ON public.activity_logs;
CREATE POLICY activity_logs_insert_tenant ON public.activity_logs
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS activity_logs_update_tenant ON public.activity_logs;
CREATE POLICY activity_logs_update_tenant ON public.activity_logs
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS activity_logs_delete_tenant ON public.activity_logs;
CREATE POLICY activity_logs_delete_tenant ON public.activity_logs
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- import_jobs ------------------------------------------------------
ALTER TABLE public.import_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS import_jobs_select_tenant ON public.import_jobs;
CREATE POLICY import_jobs_select_tenant ON public.import_jobs
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS import_jobs_insert_tenant ON public.import_jobs;
CREATE POLICY import_jobs_insert_tenant ON public.import_jobs
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS import_jobs_update_tenant ON public.import_jobs;
CREATE POLICY import_jobs_update_tenant ON public.import_jobs
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS import_jobs_delete_tenant ON public.import_jobs;
CREATE POLICY import_jobs_delete_tenant ON public.import_jobs
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- import_row_errors ------------------------------------------------
ALTER TABLE public.import_row_errors ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS import_row_errors_select_tenant ON public.import_row_errors;
CREATE POLICY import_row_errors_select_tenant ON public.import_row_errors
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS import_row_errors_insert_tenant ON public.import_row_errors;
CREATE POLICY import_row_errors_insert_tenant ON public.import_row_errors
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS import_row_errors_update_tenant ON public.import_row_errors;
CREATE POLICY import_row_errors_update_tenant ON public.import_row_errors
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS import_row_errors_delete_tenant ON public.import_row_errors;
CREATE POLICY import_row_errors_delete_tenant ON public.import_row_errors
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- provider_usage ---------------------------------------------------
ALTER TABLE public.provider_usage ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS provider_usage_select_tenant ON public.provider_usage;
CREATE POLICY provider_usage_select_tenant ON public.provider_usage
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS provider_usage_insert_tenant ON public.provider_usage;
CREATE POLICY provider_usage_insert_tenant ON public.provider_usage
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS provider_usage_update_tenant ON public.provider_usage;
CREATE POLICY provider_usage_update_tenant ON public.provider_usage
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS provider_usage_delete_tenant ON public.provider_usage;
CREATE POLICY provider_usage_delete_tenant ON public.provider_usage
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- refresh_tokens ---------------------------------------------------
ALTER TABLE public.refresh_tokens ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS refresh_tokens_select_tenant ON public.refresh_tokens;
CREATE POLICY refresh_tokens_select_tenant ON public.refresh_tokens
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS refresh_tokens_insert_tenant ON public.refresh_tokens;
CREATE POLICY refresh_tokens_insert_tenant ON public.refresh_tokens
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS refresh_tokens_update_tenant ON public.refresh_tokens;
CREATE POLICY refresh_tokens_update_tenant ON public.refresh_tokens
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS refresh_tokens_delete_tenant ON public.refresh_tokens;
CREATE POLICY refresh_tokens_delete_tenant ON public.refresh_tokens
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- team_invites -----------------------------------------------------
ALTER TABLE public.team_invites ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_invites_select_tenant ON public.team_invites;
CREATE POLICY team_invites_select_tenant ON public.team_invites
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS team_invites_insert_tenant ON public.team_invites;
CREATE POLICY team_invites_insert_tenant ON public.team_invites
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS team_invites_update_tenant ON public.team_invites;
CREATE POLICY team_invites_update_tenant ON public.team_invites
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS team_invites_delete_tenant ON public.team_invites;
CREATE POLICY team_invites_delete_tenant ON public.team_invites
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- lead_assignment_rules --------------------------------------------
ALTER TABLE public.lead_assignment_rules ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lead_assignment_rules_select_tenant ON public.lead_assignment_rules;
CREATE POLICY lead_assignment_rules_select_tenant ON public.lead_assignment_rules
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_assignment_rules_insert_tenant ON public.lead_assignment_rules;
CREATE POLICY lead_assignment_rules_insert_tenant ON public.lead_assignment_rules
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_assignment_rules_update_tenant ON public.lead_assignment_rules;
CREATE POLICY lead_assignment_rules_update_tenant ON public.lead_assignment_rules
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_assignment_rules_delete_tenant ON public.lead_assignment_rules;
CREATE POLICY lead_assignment_rules_delete_tenant ON public.lead_assignment_rules
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- lead_assignment_logs ---------------------------------------------
ALTER TABLE public.lead_assignment_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lead_assignment_logs_select_tenant ON public.lead_assignment_logs;
CREATE POLICY lead_assignment_logs_select_tenant ON public.lead_assignment_logs
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_assignment_logs_insert_tenant ON public.lead_assignment_logs;
CREATE POLICY lead_assignment_logs_insert_tenant ON public.lead_assignment_logs
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_assignment_logs_update_tenant ON public.lead_assignment_logs;
CREATE POLICY lead_assignment_logs_update_tenant ON public.lead_assignment_logs
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS lead_assignment_logs_delete_tenant ON public.lead_assignment_logs;
CREATE POLICY lead_assignment_logs_delete_tenant ON public.lead_assignment_logs
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- pipeline_stages --------------------------------------------------
ALTER TABLE public.pipeline_stages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pipeline_stages_select_tenant ON public.pipeline_stages;
CREATE POLICY pipeline_stages_select_tenant ON public.pipeline_stages
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS pipeline_stages_insert_tenant ON public.pipeline_stages;
CREATE POLICY pipeline_stages_insert_tenant ON public.pipeline_stages
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS pipeline_stages_update_tenant ON public.pipeline_stages;
CREATE POLICY pipeline_stages_update_tenant ON public.pipeline_stages
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS pipeline_stages_delete_tenant ON public.pipeline_stages;
CREATE POLICY pipeline_stages_delete_tenant ON public.pipeline_stages
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- close_reasons ----------------------------------------------------
ALTER TABLE public.close_reasons ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS close_reasons_select_tenant ON public.close_reasons;
CREATE POLICY close_reasons_select_tenant ON public.close_reasons
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS close_reasons_insert_tenant ON public.close_reasons;
CREATE POLICY close_reasons_insert_tenant ON public.close_reasons
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS close_reasons_update_tenant ON public.close_reasons;
CREATE POLICY close_reasons_update_tenant ON public.close_reasons
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS close_reasons_delete_tenant ON public.close_reasons;
CREATE POLICY close_reasons_delete_tenant ON public.close_reasons
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- tasks ------------------------------------------------------------
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tasks_select_tenant ON public.tasks;
CREATE POLICY tasks_select_tenant ON public.tasks
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS tasks_insert_tenant ON public.tasks;
CREATE POLICY tasks_insert_tenant ON public.tasks
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS tasks_update_tenant ON public.tasks;
CREATE POLICY tasks_update_tenant ON public.tasks
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS tasks_delete_tenant ON public.tasks;
CREATE POLICY tasks_delete_tenant ON public.tasks
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- notes ------------------------------------------------------------
ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notes_select_tenant ON public.notes;
CREATE POLICY notes_select_tenant ON public.notes
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS notes_insert_tenant ON public.notes;
CREATE POLICY notes_insert_tenant ON public.notes
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS notes_update_tenant ON public.notes;
CREATE POLICY notes_update_tenant ON public.notes
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS notes_delete_tenant ON public.notes;
CREATE POLICY notes_delete_tenant ON public.notes
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- workflows --------------------------------------------------------
ALTER TABLE public.workflows ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workflows_select_tenant ON public.workflows;
CREATE POLICY workflows_select_tenant ON public.workflows
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflows_insert_tenant ON public.workflows;
CREATE POLICY workflows_insert_tenant ON public.workflows
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflows_update_tenant ON public.workflows;
CREATE POLICY workflows_update_tenant ON public.workflows
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflows_delete_tenant ON public.workflows;
CREATE POLICY workflows_delete_tenant ON public.workflows
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- workflow_triggers ------------------------------------------------
ALTER TABLE public.workflow_triggers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workflow_triggers_select_tenant ON public.workflow_triggers;
CREATE POLICY workflow_triggers_select_tenant ON public.workflow_triggers
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_triggers_insert_tenant ON public.workflow_triggers;
CREATE POLICY workflow_triggers_insert_tenant ON public.workflow_triggers
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_triggers_update_tenant ON public.workflow_triggers;
CREATE POLICY workflow_triggers_update_tenant ON public.workflow_triggers
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_triggers_delete_tenant ON public.workflow_triggers;
CREATE POLICY workflow_triggers_delete_tenant ON public.workflow_triggers
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- workflow_executions ----------------------------------------------
ALTER TABLE public.workflow_executions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workflow_executions_select_tenant ON public.workflow_executions;
CREATE POLICY workflow_executions_select_tenant ON public.workflow_executions
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_executions_insert_tenant ON public.workflow_executions;
CREATE POLICY workflow_executions_insert_tenant ON public.workflow_executions
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_executions_update_tenant ON public.workflow_executions;
CREATE POLICY workflow_executions_update_tenant ON public.workflow_executions
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_executions_delete_tenant ON public.workflow_executions;
CREATE POLICY workflow_executions_delete_tenant ON public.workflow_executions
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- workflow_events --------------------------------------------------
ALTER TABLE public.workflow_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workflow_events_select_tenant ON public.workflow_events;
CREATE POLICY workflow_events_select_tenant ON public.workflow_events
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_events_insert_tenant ON public.workflow_events;
CREATE POLICY workflow_events_insert_tenant ON public.workflow_events
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_events_update_tenant ON public.workflow_events;
CREATE POLICY workflow_events_update_tenant ON public.workflow_events
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS workflow_events_delete_tenant ON public.workflow_events;
CREATE POLICY workflow_events_delete_tenant ON public.workflow_events
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- credentials ------------------------------------------------------
ALTER TABLE public.credentials ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS credentials_select_tenant ON public.credentials;
CREATE POLICY credentials_select_tenant ON public.credentials
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS credentials_insert_tenant ON public.credentials;
CREATE POLICY credentials_insert_tenant ON public.credentials
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS credentials_update_tenant ON public.credentials;
CREATE POLICY credentials_update_tenant ON public.credentials
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS credentials_delete_tenant ON public.credentials;
CREATE POLICY credentials_delete_tenant ON public.credentials
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- execution_events -------------------------------------------------
ALTER TABLE public.execution_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS execution_events_select_tenant ON public.execution_events;
CREATE POLICY execution_events_select_tenant ON public.execution_events
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS execution_events_insert_tenant ON public.execution_events;
CREATE POLICY execution_events_insert_tenant ON public.execution_events
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS execution_events_update_tenant ON public.execution_events;
CREATE POLICY execution_events_update_tenant ON public.execution_events
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS execution_events_delete_tenant ON public.execution_events;
CREATE POLICY execution_events_delete_tenant ON public.execution_events
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- ai_memories ------------------------------------------------------
ALTER TABLE public.ai_memories ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_memories_select_tenant ON public.ai_memories;
CREATE POLICY ai_memories_select_tenant ON public.ai_memories
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS ai_memories_insert_tenant ON public.ai_memories;
CREATE POLICY ai_memories_insert_tenant ON public.ai_memories
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS ai_memories_update_tenant ON public.ai_memories;
CREATE POLICY ai_memories_update_tenant ON public.ai_memories
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS ai_memories_delete_tenant ON public.ai_memories;
CREATE POLICY ai_memories_delete_tenant ON public.ai_memories
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- knowledge_items --------------------------------------------------
ALTER TABLE public.knowledge_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS knowledge_items_select_tenant ON public.knowledge_items;
CREATE POLICY knowledge_items_select_tenant ON public.knowledge_items
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS knowledge_items_insert_tenant ON public.knowledge_items;
CREATE POLICY knowledge_items_insert_tenant ON public.knowledge_items
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS knowledge_items_update_tenant ON public.knowledge_items;
CREATE POLICY knowledge_items_update_tenant ON public.knowledge_items
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS knowledge_items_delete_tenant ON public.knowledge_items;
CREATE POLICY knowledge_items_delete_tenant ON public.knowledge_items
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- agent_runs -------------------------------------------------------
ALTER TABLE public.agent_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS agent_runs_select_tenant ON public.agent_runs;
CREATE POLICY agent_runs_select_tenant ON public.agent_runs
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS agent_runs_insert_tenant ON public.agent_runs;
CREATE POLICY agent_runs_insert_tenant ON public.agent_runs
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS agent_runs_update_tenant ON public.agent_runs;
CREATE POLICY agent_runs_update_tenant ON public.agent_runs
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS agent_runs_delete_tenant ON public.agent_runs;
CREATE POLICY agent_runs_delete_tenant ON public.agent_runs
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- agent_state ------------------------------------------------------
ALTER TABLE public.agent_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS agent_state_select_tenant ON public.agent_state;
CREATE POLICY agent_state_select_tenant ON public.agent_state
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS agent_state_insert_tenant ON public.agent_state;
CREATE POLICY agent_state_insert_tenant ON public.agent_state
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS agent_state_update_tenant ON public.agent_state;
CREATE POLICY agent_state_update_tenant ON public.agent_state
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS agent_state_delete_tenant ON public.agent_state;
CREATE POLICY agent_state_delete_tenant ON public.agent_state
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- notifications ----------------------------------------------------
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notifications_select_tenant ON public.notifications;
CREATE POLICY notifications_select_tenant ON public.notifications
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS notifications_insert_tenant ON public.notifications;
CREATE POLICY notifications_insert_tenant ON public.notifications
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS notifications_update_tenant ON public.notifications;
CREATE POLICY notifications_update_tenant ON public.notifications
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS notifications_delete_tenant ON public.notifications;
CREATE POLICY notifications_delete_tenant ON public.notifications
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- approval_requests ------------------------------------------------
ALTER TABLE public.approval_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS approval_requests_select_tenant ON public.approval_requests;
CREATE POLICY approval_requests_select_tenant ON public.approval_requests
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS approval_requests_insert_tenant ON public.approval_requests;
CREATE POLICY approval_requests_insert_tenant ON public.approval_requests
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS approval_requests_update_tenant ON public.approval_requests;
CREATE POLICY approval_requests_update_tenant ON public.approval_requests
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS approval_requests_delete_tenant ON public.approval_requests;
CREATE POLICY approval_requests_delete_tenant ON public.approval_requests
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- approval_logs ----------------------------------------------------
ALTER TABLE public.approval_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS approval_logs_select_tenant ON public.approval_logs;
CREATE POLICY approval_logs_select_tenant ON public.approval_logs
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS approval_logs_insert_tenant ON public.approval_logs;
CREATE POLICY approval_logs_insert_tenant ON public.approval_logs
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS approval_logs_update_tenant ON public.approval_logs;
CREATE POLICY approval_logs_update_tenant ON public.approval_logs
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS approval_logs_delete_tenant ON public.approval_logs;
CREATE POLICY approval_logs_delete_tenant ON public.approval_logs
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- briefings --------------------------------------------------------
ALTER TABLE public.briefings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS briefings_select_tenant ON public.briefings;
CREATE POLICY briefings_select_tenant ON public.briefings
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS briefings_insert_tenant ON public.briefings;
CREATE POLICY briefings_insert_tenant ON public.briefings
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS briefings_update_tenant ON public.briefings;
CREATE POLICY briefings_update_tenant ON public.briefings
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS briefings_delete_tenant ON public.briefings;
CREATE POLICY briefings_delete_tenant ON public.briefings
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- growth_metrics ---------------------------------------------------
ALTER TABLE public.growth_metrics ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS growth_metrics_select_tenant ON public.growth_metrics;
CREATE POLICY growth_metrics_select_tenant ON public.growth_metrics
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_metrics_insert_tenant ON public.growth_metrics;
CREATE POLICY growth_metrics_insert_tenant ON public.growth_metrics
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_metrics_update_tenant ON public.growth_metrics;
CREATE POLICY growth_metrics_update_tenant ON public.growth_metrics
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_metrics_delete_tenant ON public.growth_metrics;
CREATE POLICY growth_metrics_delete_tenant ON public.growth_metrics
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- growth_forecasts ------------------------------------------------
ALTER TABLE public.growth_forecasts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS growth_forecasts_select_tenant ON public.growth_forecasts;
CREATE POLICY growth_forecasts_select_tenant ON public.growth_forecasts
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_forecasts_insert_tenant ON public.growth_forecasts;
CREATE POLICY growth_forecasts_insert_tenant ON public.growth_forecasts
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_forecasts_update_tenant ON public.growth_forecasts;
CREATE POLICY growth_forecasts_update_tenant ON public.growth_forecasts
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_forecasts_delete_tenant ON public.growth_forecasts;
CREATE POLICY growth_forecasts_delete_tenant ON public.growth_forecasts
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- business_insights ------------------------------------------------
ALTER TABLE public.business_insights ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS business_insights_select_tenant ON public.business_insights;
CREATE POLICY business_insights_select_tenant ON public.business_insights
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS business_insights_insert_tenant ON public.business_insights;
CREATE POLICY business_insights_insert_tenant ON public.business_insights
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS business_insights_update_tenant ON public.business_insights;
CREATE POLICY business_insights_update_tenant ON public.business_insights
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS business_insights_delete_tenant ON public.business_insights;
CREATE POLICY business_insights_delete_tenant ON public.business_insights
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- deliveries -------------------------------------------------------
ALTER TABLE public.deliveries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS deliveries_select_tenant ON public.deliveries;
CREATE POLICY deliveries_select_tenant ON public.deliveries
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS deliveries_insert_tenant ON public.deliveries;
CREATE POLICY deliveries_insert_tenant ON public.deliveries
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS deliveries_update_tenant ON public.deliveries;
CREATE POLICY deliveries_update_tenant ON public.deliveries
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS deliveries_delete_tenant ON public.deliveries;
CREATE POLICY deliveries_delete_tenant ON public.deliveries
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- delivery_events --------------------------------------------------
ALTER TABLE public.delivery_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS delivery_events_select_tenant ON public.delivery_events;
CREATE POLICY delivery_events_select_tenant ON public.delivery_events
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS delivery_events_insert_tenant ON public.delivery_events;
CREATE POLICY delivery_events_insert_tenant ON public.delivery_events
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS delivery_events_update_tenant ON public.delivery_events;
CREATE POLICY delivery_events_update_tenant ON public.delivery_events
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS delivery_events_delete_tenant ON public.delivery_events;
CREATE POLICY delivery_events_delete_tenant ON public.delivery_events
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- growth_health_weights --------------------------------------------
ALTER TABLE public.growth_health_weights ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS growth_health_weights_select_tenant ON public.growth_health_weights;
CREATE POLICY growth_health_weights_select_tenant ON public.growth_health_weights
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_health_weights_insert_tenant ON public.growth_health_weights;
CREATE POLICY growth_health_weights_insert_tenant ON public.growth_health_weights
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_health_weights_update_tenant ON public.growth_health_weights;
CREATE POLICY growth_health_weights_update_tenant ON public.growth_health_weights
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_health_weights_delete_tenant ON public.growth_health_weights;
CREATE POLICY growth_health_weights_delete_tenant ON public.growth_health_weights
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- growth_analyses --------------------------------------------------
ALTER TABLE public.growth_analyses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS growth_analyses_select_tenant ON public.growth_analyses;
CREATE POLICY growth_analyses_select_tenant ON public.growth_analyses
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_analyses_insert_tenant ON public.growth_analyses;
CREATE POLICY growth_analyses_insert_tenant ON public.growth_analyses
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_analyses_update_tenant ON public.growth_analyses;
CREATE POLICY growth_analyses_update_tenant ON public.growth_analyses
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_analyses_delete_tenant ON public.growth_analyses;
CREATE POLICY growth_analyses_delete_tenant ON public.growth_analyses
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- growth_scenarios -------------------------------------------------
ALTER TABLE public.growth_scenarios ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS growth_scenarios_select_tenant ON public.growth_scenarios;
CREATE POLICY growth_scenarios_select_tenant ON public.growth_scenarios
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_scenarios_insert_tenant ON public.growth_scenarios;
CREATE POLICY growth_scenarios_insert_tenant ON public.growth_scenarios
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_scenarios_update_tenant ON public.growth_scenarios;
CREATE POLICY growth_scenarios_update_tenant ON public.growth_scenarios
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_scenarios_delete_tenant ON public.growth_scenarios;
CREATE POLICY growth_scenarios_delete_tenant ON public.growth_scenarios
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- growth_recommendations -------------------------------------------
ALTER TABLE public.growth_recommendations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS growth_recommendations_select_tenant ON public.growth_recommendations;
CREATE POLICY growth_recommendations_select_tenant ON public.growth_recommendations
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_recommendations_insert_tenant ON public.growth_recommendations;
CREATE POLICY growth_recommendations_insert_tenant ON public.growth_recommendations
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_recommendations_update_tenant ON public.growth_recommendations;
CREATE POLICY growth_recommendations_update_tenant ON public.growth_recommendations
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS growth_recommendations_delete_tenant ON public.growth_recommendations;
CREATE POLICY growth_recommendations_delete_tenant ON public.growth_recommendations
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- founder_conversations --------------------------------------------
ALTER TABLE public.founder_conversations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS founder_conversations_select_tenant ON public.founder_conversations;
CREATE POLICY founder_conversations_select_tenant ON public.founder_conversations
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_conversations_insert_tenant ON public.founder_conversations;
CREATE POLICY founder_conversations_insert_tenant ON public.founder_conversations
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_conversations_update_tenant ON public.founder_conversations;
CREATE POLICY founder_conversations_update_tenant ON public.founder_conversations
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_conversations_delete_tenant ON public.founder_conversations;
CREATE POLICY founder_conversations_delete_tenant ON public.founder_conversations
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- founder_messages -------------------------------------------------
ALTER TABLE public.founder_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS founder_messages_select_tenant ON public.founder_messages;
CREATE POLICY founder_messages_select_tenant ON public.founder_messages
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_messages_insert_tenant ON public.founder_messages;
CREATE POLICY founder_messages_insert_tenant ON public.founder_messages
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_messages_update_tenant ON public.founder_messages;
CREATE POLICY founder_messages_update_tenant ON public.founder_messages
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_messages_delete_tenant ON public.founder_messages;
CREATE POLICY founder_messages_delete_tenant ON public.founder_messages
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- founder_action_proposals -----------------------------------------
ALTER TABLE public.founder_action_proposals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS founder_action_proposals_select_tenant ON public.founder_action_proposals;
CREATE POLICY founder_action_proposals_select_tenant ON public.founder_action_proposals
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_action_proposals_insert_tenant ON public.founder_action_proposals;
CREATE POLICY founder_action_proposals_insert_tenant ON public.founder_action_proposals
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_action_proposals_update_tenant ON public.founder_action_proposals;
CREATE POLICY founder_action_proposals_update_tenant ON public.founder_action_proposals
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS founder_action_proposals_delete_tenant ON public.founder_action_proposals;
CREATE POLICY founder_action_proposals_delete_tenant ON public.founder_action_proposals
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- --- intelligence_signals ---------------------------------------------
ALTER TABLE public.intelligence_signals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS intelligence_signals_select_tenant ON public.intelligence_signals;
CREATE POLICY intelligence_signals_select_tenant ON public.intelligence_signals
  FOR SELECT TO agencyos_app
  USING (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS intelligence_signals_insert_tenant ON public.intelligence_signals;
CREATE POLICY intelligence_signals_insert_tenant ON public.intelligence_signals
  FOR INSERT TO agencyos_app
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS intelligence_signals_update_tenant ON public.intelligence_signals;
CREATE POLICY intelligence_signals_update_tenant ON public.intelligence_signals
  FOR UPDATE TO agencyos_app
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
DROP POLICY IF EXISTS intelligence_signals_delete_tenant ON public.intelligence_signals;
CREATE POLICY intelligence_signals_delete_tenant ON public.intelligence_signals
  FOR DELETE TO agencyos_app
  USING (organization_id = public.tenant_org_id());

-- =====================================================================
-- 5. Instance-global tables (no tenant data; API RBAC gates access).
-- =====================================================================
-- --- system_settings --------------------------------------------------
DROP POLICY IF EXISTS system_settings_global ON public.system_settings;
CREATE POLICY system_settings_global ON public.system_settings
  FOR ALL TO agencyos_app
  USING (true)
  WITH CHECK (true);

-- --- credential_key_versions ------------------------------------------
DROP POLICY IF EXISTS credential_key_versions_global ON public.credential_key_versions;
CREATE POLICY credential_key_versions_global ON public.credential_key_versions
  FOR ALL TO agencyos_app
  USING (true)
  WITH CHECK (true);

-- --- worker_health (SELECT-only for the app role; workers write via
--                     the BYPASSRLS agencyos_worker role) ---------------
DROP POLICY IF EXISTS worker_health_select_global ON public.worker_health;
CREATE POLICY worker_health_select_global ON public.worker_health
  FOR SELECT TO agencyos_app
  USING (true);

-- =====================================================================
-- 6. Privilege grants for the application roles.
-- =====================================================================
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agencyos_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agencyos_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agencyos_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agencyos_worker;

-- Future tables created by later migrations get the same privileges.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agencyos_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agencyos_worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO agencyos_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO agencyos_worker;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- Run as a superuser. Admin (owner) connections are not affected by the
-- policies (no FORCE ROW LEVEL SECURITY), so this is a pure removal:
--
--   DROP OWNED BY agencyos_app; DROP ROLE agencyos_app;
--   DROP OWNED BY agencyos_worker; DROP ROLE agencyos_worker;
--   DROP FUNCTION IF EXISTS public.tenant_org_id();
--   DROP FUNCTION IF EXISTS public.app_get_user_by_id(uuid);
--   DROP FUNCTION IF EXISTS public.app_get_user_by_email(text);
--   DROP FUNCTION IF EXISTS public.app_find_active_user_by_email(text);
--   DROP FUNCTION IF EXISTS public.app_get_valid_refresh_token(text, timestamptz);
--   DROP FUNCTION IF EXISTS public.app_get_organization_by_slug(text);
--   DROP FUNCTION IF EXISTS public.app_slug_available(text);
--   DROP FUNCTION IF EXISTS public.app_get_team_invite_by_token_hash(text);
--
-- (DROP OWNED BY revokes the grants and drops the policies created for the
--  role, so the per-policy manual drops above are redundant but explicit.)
-- =====================================================================