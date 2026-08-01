-- RLS policies for public.outreach_messages.
ALTER TABLE public.outreach_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "outreach_messages_select_org" ON public.outreach_messages
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "outreach_messages_insert_org" ON public.outreach_messages
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "outreach_messages_update_org" ON public.outreach_messages
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "outreach_messages_delete_org" ON public.outreach_messages
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
