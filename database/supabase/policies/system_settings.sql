-- RLS policies for public.system_settings.
-- System settings are instance-global operator configuration managed via the
-- backend (service role bypasses RLS); direct anon/authenticated table access
-- stays locked down.
ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;
