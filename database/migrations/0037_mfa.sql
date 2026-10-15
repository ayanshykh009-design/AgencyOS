-- Optional TOTP two-factor authentication (Stage 3b).
--
-- MFA is opt-in per user: enrollment stores a TOTP shared secret (encrypted at
-- rest with the credential key via app/core/crypto.py), and only users who
-- complete activation get ``mfa_enabled = true``. The login challenge then
-- requires a second factor. Recovery codes provide a one-time fallback when the
-- authenticator device is lost.
--
-- ``mfa_failed_attempts`` / ``mfa_locked_until`` throttle incorrect second
-- factors with the same victim-safe policy as password login (a correct code
-- always succeeds; only incorrect codes are throttled).
--
-- The whole feature is gated by the MFA_ENABLED setting; with it off, no user
-- can enable MFA and the login path is unchanged.
--
-- Idempotent and safe for existing data.
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS mfa_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS mfa_secret_enc text;

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS mfa_failed_attempts integer NOT NULL DEFAULT 0;

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS mfa_locked_until timestamptz;

-- One-time recovery codes (hashed, single-use). No tenant column: isolation is
-- expressed through the owning user, mirroring auth_tokens (0036).
CREATE TABLE IF NOT EXISTS public.user_recovery_codes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  code_hash   text NOT NULL,
  used_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_recovery_codes_code_hash
  ON public.user_recovery_codes (code_hash);

CREATE INDEX IF NOT EXISTS ix_user_recovery_codes_user_id
  ON public.user_recovery_codes (user_id);

ALTER TABLE public.user_recovery_codes ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_recovery_codes_select_tenant ON public.user_recovery_codes
  FOR SELECT TO agencyos_app
  USING (
    user_id IN (
      SELECT id FROM public.users
      WHERE organization_id = public.tenant_org_id()
    )
  );

CREATE POLICY user_recovery_codes_insert_tenant ON public.user_recovery_codes
  FOR INSERT TO agencyos_app
  WITH CHECK (
    user_id IN (
      SELECT id FROM public.users
      WHERE organization_id = public.tenant_org_id()
    )
  );

CREATE POLICY user_recovery_codes_update_tenant ON public.user_recovery_codes
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

CREATE POLICY user_recovery_codes_delete_tenant ON public.user_recovery_codes
  FOR DELETE TO agencyos_app
  USING (
    user_id IN (
      SELECT id FROM public.users
      WHERE organization_id = public.tenant_org_id()
    )
  );

-- The MFA login challenge resolves the user by id before any tenant context is
-- active (the username/password step has not yet established a session); the
-- existing app_get_user_by_id definer (0033) is reused for that, and the
-- challenge itself is carried in a signed short-lived JWT rather than a DB row.

-- ROLLBACK
--   DROP TABLE IF EXISTS public.user_recovery_codes;
--   ALTER TABLE public.users DROP COLUMN IF EXISTS mfa_locked_until;
--   ALTER TABLE public.users DROP COLUMN IF EXISTS mfa_failed_attempts;
--   ALTER TABLE public.users DROP COLUMN IF EXISTS mfa_secret_enc;
--   ALTER TABLE public.users DROP COLUMN IF EXISTS mfa_enabled;
