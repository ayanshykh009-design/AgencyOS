-- =====================================================================
-- 0016_search_trigram_indexes.sql
-- Search acceleration (Phase 5B B6): GIN trigram indexes for the
-- substring (ILIKE '%query%') searches used by lead and task search.
--
--   * leads  first_name / last_name / company / email / position
--     (LeadRepository.search / count — five-way OR of ILIKE '%q%')
--   * tasks  title / description
--     (TaskRepository.search_tasks — OR of ILIKE '%q%')
--
-- A leading-wildcard ILIKE cannot use a plain B-tree index; pg_trgm GIN
-- indexes turn those scans into index-assisted lookups.
--
-- Backward compatibility:
--   * CREATE EXTENSION / INDEX IF NOT EXISTS are idempotent
--   * safe to run multiple times; zero data loss
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_leads_first_name_trgm
  ON public.leads USING gin (first_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_last_name_trgm
  ON public.leads USING gin (last_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_company_trgm
  ON public.leads USING gin (company gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_email_trgm
  ON public.leads USING gin (email gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_position_trgm
  ON public.leads USING gin (position gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_title_trgm
  ON public.tasks USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_description_trgm
  ON public.tasks USING gin (description gin_trgm_ops);

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_tasks_description_trgm;
-- DROP INDEX IF EXISTS public.idx_tasks_title_trgm;
-- DROP INDEX IF EXISTS public.idx_leads_position_trgm;
-- DROP INDEX IF EXISTS public.idx_leads_email_trgm;
-- DROP INDEX IF EXISTS public.idx_leads_company_trgm;
-- DROP INDEX IF EXISTS public.idx_leads_last_name_trgm;
-- DROP INDEX IF EXISTS public.idx_leads_first_name_trgm;
-- =====================================================================
