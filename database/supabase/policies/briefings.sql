-- RLS policies for public.briefings.
-- Deletion is not exposed to direct table access; briefings are regenerated
-- (service role) and removed only with their organization.
ALTER TABLE public.briefings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "briefings_select_org" ON public.briefings
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "briefings_insert_org" ON public.briefings
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "briefings_update_org" ON public.briefings
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
