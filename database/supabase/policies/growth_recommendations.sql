-- RLS policies for public.growth_recommendations (M7 Growth Intelligence).
ALTER TABLE public.growth_recommendations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "growth_recommendations_select_org" ON public.growth_recommendations
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "growth_recommendations_insert_org" ON public.growth_recommendations
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_recommendations_update_org" ON public.growth_recommendations
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_recommendations_delete_org" ON public.growth_recommendations
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
