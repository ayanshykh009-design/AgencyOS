-- RLS policies for public.knowledge_items.
ALTER TABLE public.knowledge_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "knowledge_items_select_org" ON public.knowledge_items
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "knowledge_items_insert_org" ON public.knowledge_items
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "knowledge_items_update_org" ON public.knowledge_items
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "knowledge_items_delete_org" ON public.knowledge_items
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
