-- =====================================================================
-- 01_core_seed.sql
-- Deterministic, idempotent bootstrap data for local/dev environments.
-- Fixed UUIDs make every statement re-runnable (ON CONFLICT DO NOTHING).
-- NEVER used to reset or overwrite production data.
-- =====================================================================

-- 1) Development organization ------------------------------------------
INSERT INTO public.organizations (id, name, slug, website, timezone, settings)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'AgencyOS Dev Agency',
  'agencyos-dev',
  'https://agencyos.dev',
  'UTC',
  '{"env": "development"}'::jsonb
)
ON CONFLICT (id) DO NOTHING;

-- 2) Development user (owner) ------------------------------------------
-- NOTE: no password hash stored here — auth is handled by Supabase Auth
-- / the identity provider, keyed by the same user UUID.
INSERT INTO public.users (id, organization_id, email, full_name, role, is_active)
VALUES (
  '00000000-0000-0000-0000-000000000101',
  '00000000-0000-0000-0000-000000000001',
  'dev@agencyos.local',
  'Dev Admin',
  'owner',
  true
)
ON CONFLICT (id) DO NOTHING;

-- 3) Lead sources ------------------------------------------------------
INSERT INTO public.lead_sources (id, organization_id, name, channel, description, is_active)
VALUES
  ('00000000-0000-0000-0000-000000000201',
   '00000000-0000-0000-0000-000000000001', 'Website Contact Form', 'contact_form', 'Leads from the agency website contact form', true),
  ('00000000-0000-0000-0000-000000000202',
   '00000000-0000-0000-0000-000000000001', 'LinkedIn Manual', 'linkedin', 'Manually sourced LinkedIn prospects', true),
  ('00000000-0000-0000-0000-000000000203',
   '00000000-0000-0000-0000-000000000001', 'CSV Import', 'email', 'Bulk CSV imports', true)
ON CONFLICT (id) DO NOTHING;

-- 4) Sample leads (emails lowercased; normalized keys are computed) -----
INSERT INTO public.leads (
  id, organization_id, lead_source_id, owner_user_id, status, score,
  first_name, last_name, company, position, location, email, phone, whatsapp, website, notes
)
VALUES
  ('00000000-0000-0000-0000-000000000301',
   '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000202',
   '00000000-0000-0000-0000-000000000101',
   'new', 68,
   'Ada', 'Lovelace', 'Analytical Engines Ltd', 'CTO', 'London, UK',
   'ada@example.com', '+44 20 1234 5678', NULL, 'https://www.analytical-engines.example',
   'Interested in AI personalization for cold email.'),
  ('00000000-0000-0000-0000-000000000302',
   '00000000-0000-0000-0000-000000000001',
   '00000000-0000-0000-0000-000000000203',
   NULL,
   'researching', 41,
   'Grace', 'Hopper', 'Compilers Inc', 'VP Engineering', 'New York, USA',
   'grace@example.com', NULL, '+1 212 555 0142', 'compilers.example',
   'WhatsApp-first prospect; prefers chat over email.')
ON CONFLICT (id) DO NOTHING;
