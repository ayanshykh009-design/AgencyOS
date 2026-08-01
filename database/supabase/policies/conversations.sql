-- RLS policies for public.conversations.
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "conversations_select_org" ON public.conversations
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "conversations_insert_org" ON public.conversations
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "conversations_update_org" ON public.conversations
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "conversations_delete_org" ON public.conversations
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
