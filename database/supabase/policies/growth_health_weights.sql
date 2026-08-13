-- RLS policies for public.growth_health_weights (M7 Growth Intelligence).
-- Weights are config data; org members can read, managers/admin configure via
-- the API (which applies its own GROWTH_MANAGE permission).
ALTER TABLE public.growth_health_weights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "growth_health_weights_select_org" ON public.growth_health_weights
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "growth_health_weights_insert_org" ON public.growth_health_weights
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_health_weights_update_org" ON public.growth_health_weights
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_health_weights_delete_org" ON public.growth_health_weights
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
