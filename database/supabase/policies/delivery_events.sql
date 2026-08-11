-- RLS policies for public.delivery_events.
-- Delivery timeline is managed via the backend (service role bypasses RLS);
-- direct anon/authenticated table access stays locked down.
ALTER TABLE public.delivery_events ENABLE ROW LEVEL SECURITY;
