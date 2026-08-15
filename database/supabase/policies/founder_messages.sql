-- RLS policies for public.founder_messages (M8 Founder AI Assistant).
-- Closes the M8 RLS gap: founder messages are org-tenant data and must never
-- be readable across tenants.
ALTER TABLE public.founder_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "founder_messages_select_org" ON public.founder_messages
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "founder_messages_insert_org" ON public.founder_messages
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "founder_messages_update_org" ON public.founder_messages
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "founder_messages_delete_org" ON public.founder_messages
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
