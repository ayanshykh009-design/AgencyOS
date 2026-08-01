-- RLS policies for public.leads.
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "leads_select_org" ON public.leads
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "leads_insert_org" ON public.leads
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "leads_update_org" ON public.leads
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "leads_delete_org" ON public.leads
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
