-- =====================================================================
-- 0007_auth.sql
-- Self-contained authentication support.
--
-- Phase 1 kept credentials outside this schema (Supabase Auth / external
-- identity provider). Phase 2 adds first-party email/password auth on top
-- of the existing JWT primitives (backend/app/core/security.py):
--   * users.password_hash  — Argon2id hash (nullable: external-IDP users
--     without a local password keep working; seed users are unaffected).
--   * refresh_tokens       — rotation-based refresh token storage. Only a
--     SHA-256 digest of the opaque token is persisted (never the raw token).
--
-- RLS stays intact; the backend uses the service role for administration.
-- =====================================================================

-- ---------------------------------------------------------------------
-- users: add optional local-password hash
-- ---------------------------------------------------------------------
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS password_hash text;

COMMENT ON COLUMN public.users.password_hash IS
  'Argon2id hash for first-party auth; NULL for identity-provider-only users';

-- ---------------------------------------------------------------------
-- refresh_tokens
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.refresh_tokens (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  token_hash      text NOT NULL UNIQUE,
  expires_at      timestamptz NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  revoked_at      timestamptz,
  replaced_by     uuid,
  CONSTRAINT chk_refresh_tokens_expires_at CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON public.refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON public.refresh_tokens (expires_at);

ALTER TABLE public.refresh_tokens ENABLE ROW LEVEL SECURITY;

-- Hide password hashes from the PostgREST (anon/authenticated) roles. The
-- backend service role is unaffected and still reads the column.
REVOKE SELECT (password_hash) ON public.users FROM anon, authenticated;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.refresh_tokens;
-- ALTER TABLE public.users DROP COLUMN IF EXISTS password_hash;
-- =====================================================================
