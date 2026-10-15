-- One-time TOTP recovery codes (0037), issued once when a user activates
-- MFA. Only the Argon2 hash of each code is stored; a code is single-use
-- (``used_at`` is set on successful verification). No tenant column —
-- isolation is expressed through the owning user, mirroring ``auth_tokens``.
CREATE TABLE IF NOT EXISTS public.user_recovery_codes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
  code_hash   text NOT NULL,
  used_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_recovery_codes_code_hash
  ON public.user_recovery_codes (code_hash);

CREATE INDEX IF NOT EXISTS ix_user_recovery_codes_user_id
  ON public.user_recovery_codes (user_id);
