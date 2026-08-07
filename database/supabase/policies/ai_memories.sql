-- RLS policies for public.ai_memories.
ALTER TABLE public.ai_memories ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_memories_select_org" ON public.ai_memories
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "ai_memories_insert_org" ON public.ai_memories
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "ai_memories_update_org" ON public.ai_memories
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "ai_memories_delete_org" ON public.ai_memories
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
