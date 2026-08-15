-- RLS policies for public.founder_action_proposals (M8 Founder AI Assistant).
-- Closes the M8 RLS gap: founder action proposals are org-tenant data and must
-- never be readable across tenants.
ALTER TABLE public.founder_action_proposals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "founder_action_proposals_select_org" ON public.founder_action_proposals
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "founder_action_proposals_insert_org" ON public.founder_action_proposals
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "founder_action_proposals_update_org" ON public.founder_action_proposals
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "founder_action_proposals_delete_org" ON public.founder_action_proposals
  FOR DELETE TO authenticated
  USING (organization_id = public.tenant_org_id());
