-- RLS policies for public.users.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- password_hash is never readable through PostgREST (service role unaffected).
REVOKE SELECT (password_hash) ON public.users FROM anon, authenticated;

-- Self-service profile edits must never change the tenant-membership columns
-- (role / organization_id) or the identity (email), or escalate to owner via
-- the 'users_update_own' policy. We therefore grant the authenticated
-- (PostgREST) role UPDATE on *only* the self-editable profile column
-- (full_name) and revoke table-level UPDATE, so a column-level privilege
-- cannot be defeated by a broader table-level grant (PostgreSQL does not let
-- a column REVOKE override a table-level GRANT). role / organization_id /
-- email / password_hash stay non-writable by self-service; the privileged
-- API/service path (service role / table owner) is unaffected.
REVOKE UPDATE ON public.users FROM anon, authenticated;
GRANT UPDATE (full_name) ON public.users TO authenticated;

CREATE POLICY "users_select_org" ON public.users
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "users_insert_org" ON public.users
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "users_update_own" ON public.users
  FOR UPDATE TO authenticated
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid() AND organization_id = public.tenant_org_id());

CREATE POLICY "users_delete_admin" ON public.users
  FOR DELETE TO authenticated
  USING (
    organization_id = public.tenant_org_id()
    AND EXISTS (
      SELECT 1 FROM public.users
      WHERE id = auth.uid() AND role IN ('owner', 'admin')
    )
  );
