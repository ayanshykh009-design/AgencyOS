-- RLS policies for public.import_row_errors (append-only).
ALTER TABLE public.import_row_errors ENABLE ROW LEVEL SECURITY;

CREATE POLICY "import_row_errors_select_org" ON public.import_row_errors
  FOR SELECT TO authenticated
  USING (organization_id = public.tenant_org_id());

CREATE POLICY "import_row_errors_insert_org" ON public.import_row_errors
  FOR INSERT TO authenticated
  WITH CHECK (organization_id = public.tenant_org_id());
