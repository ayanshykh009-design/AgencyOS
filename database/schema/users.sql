-- Agency users. Phase 2 added first-party auth: password_hash holds the
-- Argon2id hash (NULL for identity-provider-only accounts). Stage 3 (0036)
-- added email verification, Stage 3b (0037) added optional TOTP MFA.
CREATE TABLE IF NOT EXISTS public.users (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  email           text NOT NULL CHECK (email = lower(btrim(email)) AND email LIKE '%_@_%'),
  full_name       text NOT NULL CHECK (length(btrim(full_name)) > 0),
  role            public.user_role NOT NULL DEFAULT 'member',
  is_active       boolean NOT NULL DEFAULT true,
  password_hash   text,
  last_login_at   timestamptz,
  token_version   integer NOT NULL DEFAULT 0,
  failed_login_attempts integer NOT NULL DEFAULT 0,
  locked_until    timestamptz,
  email_verified_at timestamptz,
  email_verification_required boolean NOT NULL DEFAULT false,
  mfa_enabled     boolean NOT NULL DEFAULT false,
  mfa_secret_enc  text,
  mfa_failed_attempts integer NOT NULL DEFAULT 0,
  mfa_locked_until timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_users_org_email UNIQUE (organization_id, email)
);

CREATE INDEX IF NOT EXISTS idx_users_org ON public.users (organization_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users (email);

DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;
CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
