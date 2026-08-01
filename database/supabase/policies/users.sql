-- RLS policies for public.users.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- password_hash is never readable through PostgREST (service role unaffected).
REVOKE SELECT (password_hash) ON public.users FROM anon, authenticated;

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
