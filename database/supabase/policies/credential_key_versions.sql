-- RLS policies for public.credential_key_versions.
-- The key-version registry is managed via the backend (service role bypasses
-- RLS); direct anon/authenticated table access stays locked down.
ALTER TABLE public.credential_key_versions ENABLE ROW LEVEL SECURITY;
