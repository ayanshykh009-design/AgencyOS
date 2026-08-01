-- RLS policies for public.activity_logs (append-only audit trail).
ALTER TABLE public.activity_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "activity_logs_select_org" ON public.activity_logs
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "activity_logs_insert_org" ON public.activity_logs
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());
