-- RLS policies for public.lead_sources.
ALTER TABLE public.lead_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "lead_sources_select_org" ON public.lead_sources
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "lead_sources_insert_org" ON public.lead_sources
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "lead_sources_update_org" ON public.lead_sources
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "lead_sources_delete_org" ON public.lead_sources
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
