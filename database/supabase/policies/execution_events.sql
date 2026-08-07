-- RLS policies for public.execution_events.
-- Execution timeline is managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.execution_events ENABLE ROW LEVEL SECURITY;
