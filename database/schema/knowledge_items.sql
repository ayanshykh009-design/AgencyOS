-- knowledge_items: durable long-term knowledge (Phase 5D)
CREATE TABLE IF NOT EXISTS public.knowledge_items (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id  uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  source_memory_id uuid REFERENCES public.ai_memories (id) ON DELETE SET NULL,
  title            text NOT NULL,
  content          text NOT NULL,
  category         text NOT NULL DEFAULT 'general',
  tags             jsonb NOT NULL DEFAULT '[]',
  metadata         jsonb NOT NULL DEFAULT '{}',
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_knowledge_items_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_knowledge_items_content_not_blank CHECK (length(btrim(content)) > 0),
  CONSTRAINT chk_knowledge_items_category_not_blank CHECK (length(btrim(category)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_items_org_category
  ON public.knowledge_items (organization_id, category);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_org_created
  ON public.knowledge_items (organization_id, created_at DESC);
-- FK support (promotion provenance).
CREATE INDEX IF NOT EXISTS idx_knowledge_items_source_memory
  ON public.knowledge_items (source_memory_id);
-- Full-text / fuzzy search over knowledge text.
CREATE INDEX IF NOT EXISTS idx_knowledge_items_title_trgm
  ON public.knowledge_items USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_content_trgm
  ON public.knowledge_items USING gin (content gin_trgm_ops);

DROP TRIGGER IF EXISTS trg_knowledge_items_updated_at ON public.knowledge_items;
CREATE TRIGGER trg_knowledge_items_updated_at
  BEFORE UPDATE ON public.knowledge_items
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.knowledge_items ENABLE ROW LEVEL SECURITY;
