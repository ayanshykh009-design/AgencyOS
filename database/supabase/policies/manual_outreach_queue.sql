-- RLS policies for public.manual_outreach_queue.
ALTER TABLE public.manual_outreach_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY "manual_outreach_select_org" ON public.manual_outreach_queue
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "manual_outreach_insert_org" ON public.manual_outreach_queue
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "manual_outreach_update_org" ON public.manual_outreach_queue
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "manual_outreach_delete_org" ON public.manual_outreach_queue
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
