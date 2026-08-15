-- RLS policies for public.intelligence_signals (M9 Founder Intelligence).
ALTER TABLE public.intelligence_signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "intelligence_signals_select_org" ON public.intelligence_signals
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "intelligence_signals_insert_org" ON public.intelligence_signals
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "intelligence_signals_update_org" ON public.intelligence_signals
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "intelligence_signals_delete_org" ON public.intelligence_signals
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
