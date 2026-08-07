-- RLS policies for public.approval_requests.
-- Deletion is not exposed to direct table access: approval requests form an
-- audit trail and are removed only with their organization.
ALTER TABLE public.approval_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "approval_requests_select_org" ON public.approval_requests
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "approval_requests_insert_org" ON public.approval_requests
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "approval_requests_update_org" ON public.approval_requests
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
