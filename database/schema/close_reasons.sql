-- Close reasons: labelled won/lost closure reasons per organization.
CREATE TABLE IF NOT EXISTS public.close_reasons (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lifecycle            public.stage_lifecycle NOT NULL,
  name                 text NOT NULL CHECK (length(btrim(name)) > 0),
  is_default           boolean NOT NULL DEFAULT false,
  created_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_close_reasons_org_lifecycle_name
    UNIQUE (organization_id, lifecycle, name),
  CONSTRAINT chk_close_reasons_lifecycle CHECK (lifecycle IN ('won', 'lost'))
);

CREATE INDEX IF NOT EXISTS idx_close_reasons_org ON public.close_reasons (organization_id);
