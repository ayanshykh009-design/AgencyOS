-- RLS policies for public.business_insights.
ALTER TABLE public.business_insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "business_insights_select_org" ON public.business_insights
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "business_insights_insert_org" ON public.business_insights
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "business_insights_update_org" ON public.business_insights
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "business_insights_delete_org" ON public.business_insights
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
