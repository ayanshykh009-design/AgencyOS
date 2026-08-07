-- RLS policies for public.agent_runs.
-- Run history is managed via the backend (service role bypasses RLS); direct
-- anon/authenticated access is read-only + append + status updates. Deletion
-- is reserved for the retention sweep (service role).
ALTER TABLE public.agent_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_runs_select_org" ON public.agent_runs
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "agent_runs_insert_org" ON public.agent_runs
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "agent_runs_update_org" ON public.agent_runs
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
