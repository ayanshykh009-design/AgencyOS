-- RLS policies for public.provider_usage.
ALTER TABLE public.provider_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "provider_usage_select_org" ON public.provider_usage
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "provider_usage_insert_org" ON public.provider_usage
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "provider_usage_update_org" ON public.provider_usage
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
