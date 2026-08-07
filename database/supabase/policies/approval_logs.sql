-- RLS policies for public.approval_logs.
-- Immutable audit trail: only SELECT + INSERT are exposed; rows are never
-- updated or deleted (consistent with the other append-only tables).
ALTER TABLE public.approval_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "approval_logs_select_org" ON public.approval_logs
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "approval_logs_insert_org" ON public.approval_logs
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());
