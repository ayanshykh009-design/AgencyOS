-- Pipeline stages: org-scoped Kanban columns.
CREATE TABLE IF NOT EXISTS public.pipeline_stages (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  name                 text NOT NULL CHECK (length(btrim(name)) > 0),
  lifecycle            public.stage_lifecycle NOT NULL DEFAULT 'open',
  position             integer NOT NULL DEFAULT 0,
  is_default           boolean NOT NULL DEFAULT false,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_pipeline_stages_org_lifecycle_name
    UNIQUE (organization_id, lifecycle, name)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_stages_org_position
  ON public.pipeline_stages (organization_id, position);

DROP TRIGGER IF EXISTS trg_pipeline_stages_updated_at ON public.pipeline_stages;
CREATE TRIGGER trg_pipeline_stages_updated_at
  BEFORE UPDATE ON public.pipeline_stages
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
