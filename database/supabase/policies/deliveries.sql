-- RLS policies for public.deliveries.
-- The delivery outbox is managed via the backend (service role bypasses RLS);
-- direct anon/authenticated table access stays locked down. Like execution
-- telemetry, deliveries are not deletable through table access.
ALTER TABLE public.deliveries ENABLE ROW LEVEL SECURITY;
