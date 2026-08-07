-- ai_memories: working + long-term memory store (Phase 5D)
CREATE TABLE IF NOT EXISTS public.ai_memories (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  memory_type     public.memory_type NOT NULL DEFAULT 'working',
  scope           public.memory_scope NOT NULL,
  source_id       uuid,
  title           text,
  content         text NOT NULL,
  importance      smallint NOT NULL DEFAULT 1,
  tags            jsonb NOT NULL DEFAULT '[]',
  metadata        jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_ai_memories_content_not_blank CHECK (length(btrim(content)) > 0),
  CONSTRAINT chk_ai_memories_title_not_blank CHECK (title IS NULL OR length(btrim(title)) > 0),
  CONSTRAINT chk_ai_memories_importance_range CHECK (importance BETWEEN 1 AND 5)
);

CREATE INDEX IF NOT EXISTS idx_ai_memories_org_type
  ON public.ai_memories (organization_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_ai_memories_org_created
  ON public.ai_memories (organization_id, created_at DESC);
-- FK support (polymorphic source reference).
CREATE INDEX IF NOT EXISTS idx_ai_memories_source_id
  ON public.ai_memories (source_id);
-- Working-memory TTL sweep.
CREATE INDEX IF NOT EXISTS idx_ai_memories_working_ttl
  ON public.ai_memories (created_at) WHERE memory_type = 'working';
-- Full-text / fuzzy search over memory text.
CREATE INDEX IF NOT EXISTS idx_ai_memories_title_trgm
  ON public.ai_memories USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ai_memories_content_trgm
  ON public.ai_memories USING gin (content gin_trgm_ops);

DROP TRIGGER IF EXISTS trg_ai_memories_updated_at ON public.ai_memories;
CREATE TRIGGER trg_ai_memories_updated_at
  BEFORE UPDATE ON public.ai_memories
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.ai_memories ENABLE ROW LEVEL SECURITY;
