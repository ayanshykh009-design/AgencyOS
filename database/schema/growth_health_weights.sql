-- growth_health_weights: configurable, versioned business-health weights (M7)
CREATE TABLE IF NOT EXISTS public.growth_health_weights (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id    uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  version            integer NOT NULL,
  weights            jsonb NOT NULL,
  is_active          boolean NOT NULL DEFAULT FALSE,
  created_by_user_id uuid REFERENCES public.users (id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_health_weights_version_positive CHECK (version > 0),
  CONSTRAINT chk_growth_health_weights_weights_object CHECK (jsonb_typeof(weights) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_health_weights_org_active
  ON public.growth_health_weights (organization_id)
  WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_growth_health_weights_org_version
  ON public.growth_health_weights (organization_id, version DESC);

DROP TRIGGER IF EXISTS trg_growth_health_weights_updated_at ON public.growth_health_weights;
CREATE TRIGGER trg_growth_health_weights_updated_at
  BEFORE UPDATE ON public.growth_health_weights
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_health_weights ENABLE ROW LEVEL SECURITY;
