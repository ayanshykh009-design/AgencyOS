-- Single-use, short-lived, hashed tokens for the account-lifecycle flows
-- (0036): email verification and password reset. No tenant column of its own
-- — isolation is expressed by resolving ``user_id`` through ``users`` (RLS),
-- and pre-authentication lookups go through the SECURITY DEFINER
-- ``app_get_auth_token``. Only the SHA-256 digest is stored, never the token.
CREATE TABLE IF NOT EXISTS public.auth_tokens (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
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
