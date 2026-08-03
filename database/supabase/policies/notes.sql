-- RLS policies for public.notes.
-- Notes are managed via the backend (service role bypasses RLS); direct
-- anon/authenticated table access stays locked down.
ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
