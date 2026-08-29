-- =====================================================================
-- 0008_team_management.sql
-- Team management: new roles (manager, sales_agent), invite lifecycle.
--
-- Phase 4 team management builds on the existing users table:
--   * user_role gains 'manager' and 'sales_agent' values (VIEWER remains
--     the read-only role).
--   * team_invites stores one-time invite links; only a SHA-256 digest of
--     the raw token is persisted (mirrors refresh_tokens.token_hash).
--   * invite_status tracks pending/accepted/revoked/expired.
-- =====================================================================

-- ---------------------------------------------------------------------
-- roles: add manager + sales_agent (idempotent, PG 12+)
-- ---------------------------------------------------------------------
ALTER TYPE public.user_role ADD VALUE IF NOT EXISTS 'manager';
ALTER TYPE public.user_role ADD VALUE IF NOT EXISTS 'sales_agent';

-- ---------------------------------------------------------------------
-- invite_status enum (idempotent helper, dropped after use)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.agencyos_create_enum(p_name text, p_values text[])
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_expr text;
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = p_name
  ) THEN
    SELECT string_agg(quote_literal(v), ', ' ORDER BY ord)
      INTO v_expr
      FROM unnest(p_values) WITH ORDINALITY AS x(v, ord);
    EXECUTE format('CREATE TYPE public.%I AS ENUM (%s)', p_name, v_expr);
  END IF;
END;
$$;

SELECT public.agencyos_create_enum('invite_status', ARRAY['pending', 'accepted', 'revoked', 'expired']);

DROP FUNCTION public.agencyos_create_enum(text, text[]);

-- ---------------------------------------------------------------------
-- team_invites
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.team_invites (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  email                text NOT NULL CHECK (length(btrim(email)) > 0),
  full_name            text,
  role                 public.user_role NOT NULL DEFAULT 'member',
  token_hash           text NOT NULL UNIQUE,
  invited_by_user_id   uuid REFERENCES public.users (id) ON DELETE SET NULL,
  status               public.invite_status NOT NULL DEFAULT 'pending',
  expires_at           timestamptz NOT NULL,
  accepted_at          timestamptz,
  accepted_user_id     uuid REFERENCES public.users (id) ON DELETE SET NULL,
  revoked_at           timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_team_invites_expires_at CHECK (expires_at > created_at),
  CONSTRAINT chk_team_invites_email_normalized
    CHECK (email = lower(btrim(email)) AND email LIKE '%_@_%')
);

CREATE INDEX IF NOT EXISTS idx_team_invites_org ON public.team_invites (organization_id);
CREATE INDEX IF NOT EXISTS idx_team_invites_email ON public.team_invites (email);
CREATE INDEX IF NOT EXISTS idx_team_invites_status ON public.team_invites (status);

DROP TRIGGER IF EXISTS trg_team_invites_updated_at ON public.team_invites;

CREATE TRIGGER trg_team_invites_updated_at
  BEFORE UPDATE ON public.team_invites
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.team_invites ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.team_invites;
-- ALTER TYPE public.user_role DROP VALUE IF EXISTS 'sales_agent';
-- ALTER TYPE public.user_role DROP VALUE IF EXISTS 'manager';
-- =====================================================================
