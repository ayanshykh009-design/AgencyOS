-- RLS policies for public.lead_research.
ALTER TABLE public.lead_research ENABLE ROW LEVEL SECURITY;

CREATE POLICY "lead_research_select_org" ON public.lead_research
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "lead_research_insert_org" ON public.lead_research
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "lead_research_update_org" ON public.lead_research
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "lead_research_delete_org" ON public.lead_research
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
