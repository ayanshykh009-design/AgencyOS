-- Enrichment/research output, one row per lead.
CREATE TABLE IF NOT EXISTS public.lead_research (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id          uuid NOT NULL REFERENCES public.leads (id) ON DELETE CASCADE,
  organization_id  uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  status           text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
  company_overview text,
  pain_points      jsonb NOT NULL DEFAULT '[]'::jsonb,
  tech_stack       jsonb NOT NULL DEFAULT '[]'::jsonb,
  recent_news      jsonb NOT NULL DEFAULT '[]'::jsonb,
  linkedin_summary text,
  icp_match_score  integer CHECK (icp_match_score IS NULL OR (icp_match_score >= 0 AND icp_match_score <= 100)),
  raw_data         jsonb NOT NULL DEFAULT '{}'::jsonb,
  research_source  text,
  researched_at    timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_lead_research_lead UNIQUE (lead_id)
);

CREATE INDEX IF NOT EXISTS idx_lead_research_org ON public.lead_research (organization_id);

DROP TRIGGER IF EXISTS trg_lead_research_updated_at ON public.lead_research;
CREATE TRIGGER trg_lead_research_updated_at
  BEFORE UPDATE ON public.lead_research
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
