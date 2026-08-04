-- RLS policies for public.workflow_events.
-- Workflow events are managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.workflow_events ENABLE ROW LEVEL SECURITY;