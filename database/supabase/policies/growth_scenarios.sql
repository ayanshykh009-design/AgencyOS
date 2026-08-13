-- RLS policies for public.growth_scenarios (M7 Growth Intelligence).
ALTER TABLE public.growth_scenarios ENABLE ROW LEVEL SECURITY;

CREATE POLICY "growth_scenarios_select_org" ON public.growth_scenarios
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "growth_scenarios_insert_org" ON public.growth_scenarios
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_scenarios_update_org" ON public.growth_scenarios
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_scenarios_delete_org" ON public.growth_scenarios
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
