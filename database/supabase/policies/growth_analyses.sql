-- RLS policies for public.growth_analyses (M7 Growth Intelligence).
-- Reads are org-scoped; writes are permitted for org members via the API.
-- Deletion is not exposed to direct table access (the retention sweep and the
-- service layer manage lifecycle).
ALTER TABLE public.growth_analyses ENABLE ROW LEVEL SECURITY;

CREATE POLICY "growth_analyses_select_org" ON public.growth_analyses
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "growth_analyses_insert_org" ON public.growth_analyses
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "growth_analyses_update_org" ON public.growth_analyses
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
