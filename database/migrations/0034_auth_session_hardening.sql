-- Auth/session hardening (Stage 1): revocable access tokens + per-account
-- failed-login throttling state.
--
-- token_version
--   Included as the ``tv`` claim in every access JWT; a mismatch against
--   ``users.token_version`` makes the token invalid. Logout and password-change
--   increment this counter, so a stolen access token stops working immediately
--   (previously a stateless access token stayed valid until ``exp``, i.e. up to
--   ACCESS_TOKEN_EXPIRE_MINUTES after logout).
--
-- failed_login_attempts / locked_until
--   Per-account brute-force throttling state. The lock only throttles
--   *incorrect* password attempts; a correct password always still
--   authenticates, so an attacker cannot deny service to a legitimate user by
--   deliberately failing their login. The counter resets on a successful login.
--
-- Idempotent and safe for existing data: columns are added with safe defaults
-- in place (existing rows get token_version = 0, failed_login_attempts = 0,
-- locked_until = NULL, preserving every current session and account). No RLS
-- change — ``users`` already carries the tenant policies from 0033.
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS token_version integer NOT NULL DEFAULT 0;

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS failed_login_attempts integer NOT NULL DEFAULT 0;

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS locked_until timestamptz;
