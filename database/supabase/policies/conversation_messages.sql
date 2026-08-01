-- RLS policies for public.conversation_messages (append-only).
ALTER TABLE public.conversation_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "conversation_messages_select_org" ON public.conversation_messages
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "conversation_messages_insert_org" ON public.conversation_messages
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());
