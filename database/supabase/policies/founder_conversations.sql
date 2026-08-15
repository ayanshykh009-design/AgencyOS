-- RLS policies for public.founder_conversations (M8 Founder AI Assistant).
-- Closes the M8 RLS gap: founder conversations are org-tenant data and must
-- never be readable across tenants.
ALTER TABLE public.founder_conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "founder_conversations_select_org" ON public.founder_conversations
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "founder_conversations_insert_org" ON public.founder_conversations
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "founder_conversations_update_org" ON public.founder_conversations
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "founder_conversations_delete_org" ON public.founder_conversations
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
