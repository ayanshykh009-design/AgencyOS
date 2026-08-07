-- RLS policies for public.notifications.
-- Deletion is not exposed to direct table access; the retention sweep
-- (service role) prunes old rows after NOTIFICATION_RETENTION_DAYS.
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "notifications_select_org" ON public.notifications
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "notifications_insert_org" ON public.notifications
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());

CREATE POLICY "notifications_update_org" ON public.notifications
  FOR UPDATE TO authenticated
  USING (organization_id = public.tenant_org_id())
  WITH CHECK (organization_id = public.tenant_org_id());
