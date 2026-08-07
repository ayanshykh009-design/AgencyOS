-- RLS policies for public.worker_health.
-- Worker health is managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.worker_health ENABLE ROW LEVEL SECURITY;
