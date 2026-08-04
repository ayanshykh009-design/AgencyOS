-- RLS policies for public.credentials.
-- Credentials are managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.credentials ENABLE ROW LEVEL SECURITY;