-- RLS policies for public.team_invites.
-- Invites are consumed via the backend (service role bypasses RLS). Keep the
-- table locked down by default: no direct anon/authenticated access.
ALTER TABLE public.team_invites ENABLE ROW LEVEL SECURITY;
