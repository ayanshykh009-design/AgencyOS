-- RLS policies for public.lead_assignment_logs.
-- Append-only trail; backend service role writes via the API.
ALTER TABLE public.lead_assignment_logs ENABLE ROW LEVEL SECURITY;
