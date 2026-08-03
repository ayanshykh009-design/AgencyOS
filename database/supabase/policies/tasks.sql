-- RLS policies for public.tasks.
-- Tasks are managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
