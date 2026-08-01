-- RLS policies for public.follow_ups.
ALTER TABLE public.follow_ups ENABLE ROW LEVEL SECURITY;

CREATE POLICY "follow_ups_select_org" ON public.follow_ups
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "follow_ups_insert_org" ON public.follow_ups
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "follow_ups_update_org" ON public.follow_ups
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "follow_ups_delete_org" ON public.follow_ups
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
