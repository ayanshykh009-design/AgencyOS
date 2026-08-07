-- RLS policies for public.agent_state.
-- Agent health bookkeeping is managed via the backend (service role bypasses
-- RLS); direct anon/authenticated access is read-only + insert + upsert.
-- Deletion is not exposed; rows are removed with their organization.
ALTER TABLE public.agent_state ENABLE ROW LEVEL SECURITY;

CREATE POLICY "agent_state_select_org" ON public.agent_state
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "agent_state_insert_org" ON public.agent_state
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "agent_state_update_org" ON public.agent_state
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
