-- RLS policies for public.close_reasons.
-- Close reasons are managed via the backend (service role bypasses RLS);
-- direct anon/authenticated table access stays locked down.
ALTER TABLE public.close_reasons ENABLE ROW LEVEL SECURITY;
