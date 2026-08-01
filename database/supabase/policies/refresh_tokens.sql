-- RLS policies for public.refresh_tokens.
-- Members can list and revoke their own refresh tokens; the backend service
-- role (rotation during /auth/refresh) bypasses RLS.
ALTER TABLE public.refresh_tokens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "refresh_tokens_select_own" ON public.refresh_tokens
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY "refresh_tokens_delete_own" ON public.refresh_tokens
  FOR DELETE TO authenticated
  USING (user_id = auth.uid());
