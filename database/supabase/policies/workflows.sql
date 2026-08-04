-- RLS policies for public.workflows.
-- Workflows are managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.workflows ENABLE ROW LEVEL SECURITY;