-- RLS policies for public.pipeline_stages.
-- Stages are managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.pipeline_stages ENABLE ROW LEVEL SECURITY;
