-- Team invites: one-time membership links. Only the SHA-256 digest of the
-- raw token is stored — never the token itself (mirrors refresh_tokens).
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
