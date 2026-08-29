-- =====================================================================
-- 0002_tenant_identity.sql
-- Multi-tenancy root: organizations + users, plus the shared
-- updated_at trigger used by every mutable table.
-- =====================================================================

-- gen_random_uuid() is core since PostgreSQL 13; keep pgcrypto around for
-- Supabase compatibility (uuid_generate_v4()).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Shared trigger: refresh updated_at on every row update.
-- clock_timestamp() (not now()) so the value advances even when the update
-- happens inside the same transaction as the insert.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = clock_timestamp();
  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------
-- organizations
-- ---------------------------------------------------------------------
CREATE TABLE public.organizations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL CHECK (length(btrim(name)) > 0),
  slug        text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
  website     text,
  timezone    text NOT NULL DEFAULT 'UTC',
  settings    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_organizations_slug UNIQUE (slug)
);

CREATE INDEX IF NOT EXISTS idx_organizations_name ON public.organizations (lower(name));

DROP TRIGGER IF EXISTS trg_organizations_updated_at ON public.organizations;

CREATE TRIGGER trg_organizations_updated_at
  BEFORE UPDATE ON public.organizations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- users
-- NOTE: no passwords/API keys stored here. Auth tokens and credentials
-- live outside this schema (Supabase Auth / external identity provider).
-- ---------------------------------------------------------------------
CREATE TABLE public.users (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  email           text NOT NULL CHECK (email = lower(btrim(email)) AND email LIKE '%_@_%'),
  full_name       text NOT NULL CHECK (length(btrim(full_name)) > 0),
  role            public.user_role NOT NULL DEFAULT 'member',
  is_active       boolean NOT NULL DEFAULT true,
  last_login_at   timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  -- Org-scoped unique email: one account per email within an organization.
  CONSTRAINT uq_users_org_email UNIQUE (organization_id, email)
);

CREATE INDEX IF NOT EXISTS idx_users_org ON public.users (organization_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users (email);

DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------
-- RLS
-- Every tenant-scoped table enables RLS in the same migration that creates
-- it. Actual policies live in database/supabase/policies/ and are applied
-- in the Supabase-managed environment.
-- ---------------------------------------------------------------------
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.users;
-- DROP TABLE IF EXISTS public.organizations;
-- DROP FUNCTION IF EXISTS public.set_updated_at();
-- =====================================================================
