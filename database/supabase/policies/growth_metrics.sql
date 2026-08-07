-- RLS policies for public.growth_metrics.
-- Deletion is not exposed to direct table access; the retention sweep
-- (service role) prunes old rows after GROWTH_METRICS_RETENTION_DAYS.
ALTER TABLE public.growth_metrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY "growth_metrics_select_org" ON public.growth_metrics
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "growth_metrics_insert_org" ON public.growth_metrics
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_metrics_update_org" ON public.growth_metrics
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
