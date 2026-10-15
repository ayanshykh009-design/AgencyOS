-- Account lifecycle hardening (Stage 3):
--   * email verification for new accounts,
--   * self-service password reset.
--
-- Both flows are driven by single-use, short-lived, hashed tokens stored in
-- ``auth_tokens``. The table carries no tenant column of its own; tenant
-- isolation is expressed by resolving ``user_id`` through ``users`` (RLS), and
-- pre-authentication lookups go through the SECURITY DEFINER
-- ``app_get_auth_token`` (a token is presented before any session exists).
--
-- Email verification is opt-in per deployment (EMAIL_VERIFICATION_ENABLED) and
-- applied to NEW accounts only: existing rows keep
-- ``email_verification_required = false`` so nobody is retroactively locked
-- out. ``email_verified_at`` records when a user confirmed ownership.
--
-- Idempotent and safe for existing data.
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS email_verified_at timestamptz;

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS email_verification_required boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS public.auth_tokens (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  purpose     text NOT NULL,
  token_hash  text NOT NULL,
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_auth_tokens_purpose
    CHECK (purpose IN ('email_verification', 'password_reset'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_tokens_token_hash
  ON public.auth_tokens (token_hash);

CREATE INDEX IF NOT EXISTS ix_auth_tokens_user_purpose
  ON public.auth_tokens (user_id, purpose);

ALTER TABLE public.auth_tokens ENABLE ROW LEVEL SECURITY;

-- Tenant-scoped policies: a token is visible/writable only within the
-- organization that owns its user. Rows are never addressed by organization
-- directly, so the predicate resolves ownership through ``users`` (which is
-- itself scoped by ``tenant_org_id()``).
CREATE POLICY auth_tokens_select_tenant ON public.auth_tokens
  FOR SELECT TO agencyos_app
  USING (
    user_id IN (
      SELECT id FROM public.users
      WHERE organization_id = public.tenant_org_id()
    )
  );

CREATE POLICY auth_tokens_insert_tenant ON public.auth_tokens
  FOR INSERT TO agencyos_app
  WITH CHECK (
    user_id IN (
      SELECT id FROM public.users
      WHERE organization_id = public.tenant_org_id()
    )
  );

CREATE POLICY auth_tokens_update_tenant ON public.auth_tokens
  FOR UPDATE TO agencyos_app
  USING (
    user_id IN (
      SELECT id FROM public.users
      WHERE organization_id = public.tenant_org_id()
    )
  )
  WITH CHECK (
    user_id IN (
      SELECT id FROM public.users
      WHERE organization_id = public.tenant_org_id()
    )
  );

CREATE POLICY auth_tokens_delete_tenant ON public.auth_tokens
  FOR DELETE TO agencyos_app
  USING (
    user_id IN (
      SELECT id FROM public.users
      WHERE organization_id = public.tenant_org_id()
    )
  );

-- Pre-authentication token resolution (verify / reset links are clicked with
-- no session). SECURITY DEFINER so RLS cannot hide the row; the token digest
-- is unguessable and single-purpose, and the caller activates the token's
-- organization immediately afterwards.
CREATE OR REPLACE FUNCTION public.app_get_auth_token(p_token_hash text)
RETURNS SETOF public.auth_tokens
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT * FROM public.auth_tokens WHERE token_hash = p_token_hash;
$$;

REVOKE ALL ON FUNCTION public.app_get_auth_token(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.app_get_auth_token(text) TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.app_get_auth_token(text) TO agencyos_worker;

-- ROLLBACK
--   DROP FUNCTION IF EXISTS public.app_get_auth_token(text);
--   DROP TABLE IF EXISTS public.auth_tokens;
--   ALTER TABLE public.users DROP COLUMN IF EXISTS email_verification_required;
--   ALTER TABLE public.users DROP COLUMN IF EXISTS email_verified_at;
