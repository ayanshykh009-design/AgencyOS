-- Auth hardening (Stage 2): refresh-token *reuse detection*.
--
-- A refresh-token family tracks a single logical session: the first token
-- issued at login/register opens a family, and every rotation inherits the
-- same ``family_id``. When a token that has already been rotated (i.e. was
-- revoked because it was exchanged for a successor) is presented again, the
-- token has leaked: we treat it as a replay, revoke the *whole* family, and
-- bump the user's ``token_version`` so every outstanding access token is
-- invalidated too. The legitimate holder is forced to re-authenticate, while
-- the attacker can no longer silently ride the rotated chain.
--
-- This is the token-theft-detection complement to the stateless access-token
-- revocation (``users.token_version`` / ``tv`` claim) added in 0034.
--
-- Idempotent and safe for existing data: ``family_id`` is backfilled to the
-- row's own id (each existing token is treated as its own single-token
-- family), so no live session is broken by applying this migration.
ALTER TABLE public.refresh_tokens
  ADD COLUMN IF NOT EXISTS family_id uuid;

UPDATE public.refresh_tokens SET family_id = id WHERE family_id IS NULL;

ALTER TABLE public.refresh_tokens ALTER COLUMN family_id SET NOT NULL;

ALTER TABLE public.refresh_tokens
  ALTER COLUMN family_id SET DEFAULT gen_random_uuid();

CREATE INDEX IF NOT EXISTS ix_refresh_tokens_family_id
  ON public.refresh_tokens (family_id);

-- Reuse detection needs to see *revoked* rows too (the replay of a rotated
-- token is exactly a revoked row), so the existing
-- ``app_get_valid_refresh_token`` (which filters revoked/expired) is not
-- enough. This SECURITY DEFINER lookup resolves a token by digest regardless
-- of state, before any tenant context exists (refresh runs pre-auth, so RLS
-- would otherwise hide the row).
CREATE OR REPLACE FUNCTION public.app_get_refresh_token_any(p_token_hash text)
RETURNS SETOF public.refresh_tokens
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT * FROM public.refresh_tokens WHERE token_hash = p_token_hash;
$$;

REVOKE ALL ON FUNCTION public.app_get_refresh_token_any(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.app_get_refresh_token_any(text) TO agencyos_app;
GRANT EXECUTE ON FUNCTION public.app_get_refresh_token_any(text) TO agencyos_worker;

-- ROLLBACK
--   DROP FUNCTION IF EXISTS public.app_get_refresh_token_any(text);
--   DROP INDEX IF EXISTS public.ix_refresh_tokens_family_id;
--   ALTER TABLE public.refresh_tokens DROP COLUMN IF EXISTS family_id;
