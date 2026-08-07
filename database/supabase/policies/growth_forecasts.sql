-- RLS policies for public.growth_forecasts.
-- Deletion is not exposed to direct table access; forecasts are regenerated
-- (service role) and removed only with their organization.
ALTER TABLE public.growth_forecasts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "growth_forecasts_select_org" ON public.growth_forecasts
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "growth_forecasts_insert_org" ON public.growth_forecasts
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_forecasts_update_org" ON public.growth_forecasts
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
