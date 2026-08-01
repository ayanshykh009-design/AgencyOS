-- RLS policies for public.outreach_attempts.
ALTER TABLE public.outreach_attempts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "outreach_attempts_select_org" ON public.outreach_attempts
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "outreach_attempts_insert_org" ON public.outreach_attempts
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "outreach_attempts_update_org" ON public.outreach_attempts
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "outreach_attempts_delete_org" ON public.outreach_attempts
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
