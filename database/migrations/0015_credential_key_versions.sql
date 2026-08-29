-- =====================================================================
-- 0015_credential_key_versions.sql
-- Credential key management (Phase 5B B1): envelope encryption + key
-- versioning + rotation support.
--
--   * credentials.key_version      — version label of the key that encrypted
--                                    the stored value ('0' = pre-versioning
--                                    legacy rows; upgraded by the rekey worker)
--   * credentials.last_rotated_at  — when the value was last re-encrypted
--   * credential_key_versions      — registry/audit of known key versions
--                                    (fingerprint, active/retired lifecycle)
--
-- Backward compatibility:
--   * additive columns only; NOT NULL with a fast DEFAULT so existing rows
--     are filled with '0' without a table rewrite or any row mutation
--   * CREATE INDEX / TABLE IF NOT EXISTS are idempotent
--   * safe to run multiple times; zero data loss
-- =====================================================================

ALTER TABLE public.credentials
  ADD COLUMN IF NOT EXISTS key_version text NOT NULL DEFAULT '0';

ALTER TABLE public.credentials
  ADD COLUMN IF NOT EXISTS last_rotated_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_credentials_key_version
  ON public.credentials (key_version);

CREATE TABLE IF NOT EXISTS public.credential_key_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version text NOT NULL UNIQUE,
  key_fingerprint text NOT NULL,
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'retired')),
  retired_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_credential_key_versions_updated_at
  ON public.credential_key_versions;

CREATE TRIGGER trg_credential_key_versions_updated_at
  BEFORE UPDATE ON public.credential_key_versions
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.credential_key_versions ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.credential_key_versions;
-- ALTER TABLE public.credentials DROP COLUMN IF EXISTS last_rotated_at;
-- ALTER TABLE public.credentials DROP COLUMN IF EXISTS key_version;
-- =====================================================================
