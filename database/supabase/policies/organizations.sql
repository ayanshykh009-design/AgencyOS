-- RLS policies for public.organizations.
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "organizations_select_own" ON public.organizations
  FOR SELECT TO authenticated
  USING (id = public.tenant_org_id());

CREATE POLICY "organizations_insert_own" ON public.organizations
  FOR INSERT TO authenticated
  WITH CHECK (id = public.tenant_org_id());

CREATE POLICY "organizations_update_admin" ON public.organizations
  FOR UPDATE TO authenticated
  USING (id = public.tenant_org_id())
  WITH CHECK (id = public.tenant_org_id());

CREATE POLICY "organizations_delete_owner" ON public.organizations
  FOR DELETE TO authenticated
  USING (
    id = public.tenant_org_id()
    AND EXISTS (
      SELECT 1 FROM public.users
      WHERE id = auth.uid() AND role = 'owner'
    )
  );
