-- RLS policies for public.workflow_executions.
-- Workflow executions are managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.workflow_executions ENABLE ROW LEVEL SECURITY;