-- Shared RLS helper: resolve the caller's organization from Supabase Auth.
-- `auth.uid()` is provided by Supabase Auth (resolves to NULL elsewhere).
CREATE OR REPLACE FUNCTION public.tenant_org_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT organization_id
  FROM public.users
  WHERE id = auth.uid() AND is_active
$$;
