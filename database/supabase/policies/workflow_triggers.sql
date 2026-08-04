-- RLS policies for public.workflow_triggers.
-- Workflow triggers are managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.workflow_triggers ENABLE ROW LEVEL SECURITY;