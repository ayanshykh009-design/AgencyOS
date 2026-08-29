-- =====================================================================
-- 0018_phase5d_database_layer.sql
-- Phase 5D: AI intelligence layer — database layer.
--
--   * memory_type / memory_scope             — labels for AI memory storage
--   * ai_memories                            — working + long-term memory store
--   * knowledge_items                        — durable long-term knowledge
--   * agent_run_status / agent_run_trigger   — labels for agent run bookkeeping
--   * agent_runs                             — per-run execution records
--   * agent_state_status / agent_health      — labels for agent runtime health
--   * agent_state                            — per-agent health bookkeeping
--   * notification_type                      — labels for in-app notifications
--   * notifications                          — in-app notification inbox
--   * approval_request_status                — labels for gated approvals
--   * approval_requests                      — workflow-gated approval requests
--   * approval_log_action                    — labels for the approval audit log
--   * approval_logs                          — immutable approval audit trail
--   * briefing_type                          — labels for founder briefings
--   * briefings                              — generated founder briefings
--   * growth_metrics                         — periodized growth/performance rows
--   * growth_forecasts                       — deterministic growth forecasts
--   * insight_type / insight_severity / insight_status — labels for insights
--   * business_insights                      — generated business insight rows
--
-- Backward compatibility:
--   * additive only (new tables, new enum types; nothing existing is touched)
--   * CREATE TABLE / INDEX / TRIGGER IF NOT EXISTS are idempotent
--   * enum creation guarded by pg_type existence checks
--   * safe to run multiple times; zero data loss
-- =====================================================================

-- ---------------------------------------------------------------------
-- memory_type: working (ephemeral, TTL-managed) vs long_term (durable).
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'memory_type'
  ) THEN
    CREATE TYPE public.memory_type AS ENUM ('working', 'long_term');
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- memory_scope: where a memory came from / applies to.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'memory_scope'
  ) THEN
    CREATE TYPE public.memory_scope AS ENUM (
      'conversation', 'research', 'workflow', 'shared_context', 'knowledge', 'manual'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- agent_run_status: lifecycle of a single agent run.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'agent_run_status'
  ) THEN
    CREATE TYPE public.agent_run_status AS ENUM (
      'queued', 'running', 'succeeded', 'failed', 'cancelled'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- agent_run_trigger: how a run was started.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'agent_run_trigger'
  ) THEN
    CREATE TYPE public.agent_run_trigger AS ENUM (
      'manual', 'schedule', 'workflow', 'event'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- agent_state_status: lifecycle of an agent definition.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'agent_state_status'
  ) THEN
    CREATE TYPE public.agent_state_status AS ENUM (
      'active', 'paused', 'degraded', 'disabled'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- agent_health: rolling health signal for an agent.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'agent_health'
  ) THEN
    CREATE TYPE public.agent_health AS ENUM ('healthy', 'degraded', 'unhealthy');
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- notification_type: in-app notification categories.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'notification_type'
  ) THEN
    CREATE TYPE public.notification_type AS ENUM (
      'approval_request', 'approval_result', 'workflow_event',
      'agent_event', 'system', 'briefing', 'insight'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- approval_request_status: lifecycle of a gated approval request.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'approval_request_status'
  ) THEN
    CREATE TYPE public.approval_request_status AS ENUM (
      'pending', 'approved', 'denied', 'expired', 'cancelled'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- approval_log_action: actions recorded in the immutable approval audit log.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'approval_log_action'
  ) THEN
    CREATE TYPE public.approval_log_action AS ENUM (
      'requested', 'notified', 'approved', 'denied', 'expired', 'cancelled'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- briefing_type: cadence of generated founder briefings.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'briefing_type'
  ) THEN
    CREATE TYPE public.briefing_type AS ENUM ('daily', 'weekly', 'manual');
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- insight_type: category of a generated business insight.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'insight_type'
  ) THEN
    CREATE TYPE public.insight_type AS ENUM (
      'opportunity', 'risk', 'trend', 'anomaly', 'recommendation'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- insight_severity: urgency of a business insight.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'insight_severity'
  ) THEN
    CREATE TYPE public.insight_severity AS ENUM (
      'info', 'low', 'medium', 'high', 'critical'
    );
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- insight_status: triage lifecycle of a business insight.
-- ---------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = 'insight_status'
  ) THEN
    CREATE TYPE public.insight_status AS ENUM ('active', 'acknowledged', 'dismissed');
  END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- ai_memories: working + long-term memory store (org-scoped).
-- Working memories are ephemeral: rows older than the configured TTL
-- (MEMORY_WORKING_TTL_DAYS) are eligible for cleanup. Long-term memories
-- are durable and never auto-deleted.
-- ---------------------------------------------------------------------
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

-- Tenant-scoped lookups.
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
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_ai_memories_title_trgm
  ON public.ai_memories USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_ai_memories_content_trgm
  ON public.ai_memories USING gin (content gin_trgm_ops);

DROP TRIGGER IF EXISTS trg_ai_memories_updated_at ON public.ai_memories;

CREATE TRIGGER trg_ai_memories_updated_at
  BEFORE UPDATE ON public.ai_memories
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.ai_memories ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- knowledge_items: durable long-term knowledge (org-scoped).
-- Optionally promoted from a working memory (source_memory_id).
-- ---------------------------------------------------------------------
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

-- Tenant-scoped lookups.
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

-- ---------------------------------------------------------------------
-- agent_runs: per-run execution records for the agent runtime.
-- Retention is configurable (AGENT_RUN_RETENTION_DAYS); rows are pruned
-- on created_at by the retention sweep.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.agent_runs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  agent_name      text NOT NULL,
  status          public.agent_run_status NOT NULL DEFAULT 'queued',
  trigger         public.agent_run_trigger NOT NULL DEFAULT 'manual',
  workflow_id     uuid REFERENCES public.workflows (id) ON DELETE SET NULL,
  input           jsonb NOT NULL DEFAULT '{}',
  output          jsonb,
  error           text,
  duration_ms     integer,
  cost            numeric(18, 6) NOT NULL DEFAULT 0,
  started_at      timestamptz,
  finished_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_agent_runs_agent_name_not_blank CHECK (length(btrim(agent_name)) > 0),
  CONSTRAINT chk_agent_runs_duration_nonneg CHECK (duration_ms IS NULL OR duration_ms >= 0),
  CONSTRAINT chk_agent_runs_cost_nonneg CHECK (cost >= 0)
);

-- Tenant-scoped lookups.
CREATE INDEX IF NOT EXISTS idx_agent_runs_org_status
  ON public.agent_runs (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_runs_org_agent_created
  ON public.agent_runs (organization_id, agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_org_created
  ON public.agent_runs (organization_id, created_at DESC);
-- FK support (workflow-triggered runs).
CREATE INDEX IF NOT EXISTS idx_agent_runs_org_workflow
  ON public.agent_runs (organization_id, workflow_id);
-- Configurable-retention sweep.
CREATE INDEX IF NOT EXISTS idx_agent_runs_created_retention
  ON public.agent_runs (created_at);

DROP TRIGGER IF EXISTS trg_agent_runs_updated_at ON public.agent_runs;

CREATE TRIGGER trg_agent_runs_updated_at
  BEFORE UPDATE ON public.agent_runs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.agent_runs ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- agent_state: rolling health bookkeeping for the agent runtime.
-- One row per (organization, agent_name); updated as runs complete.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.agent_state (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  agent_name        text NOT NULL,
  status            public.agent_state_status NOT NULL DEFAULT 'active',
  health            public.agent_health NOT NULL DEFAULT 'healthy',
  queue_depth       integer NOT NULL DEFAULT 0,
  total_runs        integer NOT NULL DEFAULT 0,
  average_runtime_ms numeric(12, 2) NOT NULL DEFAULT 0,
  average_cost      numeric(18, 6) NOT NULL DEFAULT 0,
  last_execution    timestamptz,
  last_error        text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_agent_state_agent_name_not_blank CHECK (length(btrim(agent_name)) > 0),
  CONSTRAINT chk_agent_state_queue_depth_nonneg CHECK (queue_depth >= 0),
  CONSTRAINT chk_agent_state_total_runs_nonneg CHECK (total_runs >= 0),
  CONSTRAINT chk_agent_state_avg_runtime_nonneg CHECK (average_runtime_ms >= 0),
  CONSTRAINT chk_agent_state_avg_cost_nonneg CHECK (average_cost >= 0)
);

-- One state row per agent within an organization.
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_state_org_agent
  ON public.agent_state (organization_id, agent_name);
-- Global fleet-health scans (operator monitoring).
CREATE INDEX IF NOT EXISTS idx_agent_state_status_health
  ON public.agent_state (status, health);

DROP TRIGGER IF EXISTS trg_agent_state_updated_at ON public.agent_state;

CREATE TRIGGER trg_agent_state_updated_at
  BEFORE UPDATE ON public.agent_state
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.agent_state ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- notifications: in-app notification inbox (per-user, org-scoped).
-- Rows are pruned after NOTIFICATION_RETENTION_DAYS by the retention sweep.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notifications (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  user_id         uuid REFERENCES public.users (id) ON DELETE SET NULL,
  type            public.notification_type NOT NULL,
  title           text NOT NULL,
  body            text NOT NULL,
  action_url      text,
  is_read         boolean NOT NULL DEFAULT false,
  read_at         timestamptz,
  metadata        jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_notifications_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_notifications_body_not_blank CHECK (length(btrim(body)) > 0)
);

-- Tenant inbox queries (incl. unread badge).
CREATE INDEX IF NOT EXISTS idx_notifications_org_user_read
  ON public.notifications (organization_id, user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
  ON public.notifications (user_id) WHERE is_read = false;
CREATE INDEX IF NOT EXISTS idx_notifications_org_created
  ON public.notifications (organization_id, created_at DESC);
-- Retention sweep.
CREATE INDEX IF NOT EXISTS idx_notifications_created_retention
  ON public.notifications (created_at);

DROP TRIGGER IF EXISTS trg_notifications_updated_at ON public.notifications;

CREATE TRIGGER trg_notifications_updated_at
  BEFORE UPDATE ON public.notifications
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- approval_requests: workflow-gated approval requests (org-scoped).
-- Pending requests auto-expire (deny) at expires_at; the default matches
-- APPROVAL_EXPIRY_HOURS (24h). expires_at is set explicitly by the service.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.approval_requests (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  workflow_id           uuid REFERENCES public.workflows (id) ON DELETE SET NULL,
  workflow_execution_id uuid REFERENCES public.workflow_executions (id) ON DELETE SET NULL,
  requested_by_user_id  uuid REFERENCES public.users (id) ON DELETE SET NULL,
  approver_user_id      uuid REFERENCES public.users (id) ON DELETE SET NULL,
  title                 text NOT NULL,
  details               text,
  status                public.approval_request_status NOT NULL DEFAULT 'pending',
  expires_at            timestamptz NOT NULL DEFAULT (now() + interval '24 hours'),
  decided_by_user_id    uuid REFERENCES public.users (id) ON DELETE SET NULL,
  decided_at            timestamptz,
  decision_note         text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_approval_requests_title_not_blank CHECK (length(btrim(title)) > 0)
);

-- Tenant-scoped lookups.
CREATE INDEX IF NOT EXISTS idx_approval_requests_org_status
  ON public.approval_requests (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_approval_requests_org_approver_status
  ON public.approval_requests (organization_id, approver_user_id, status);
CREATE INDEX IF NOT EXISTS idx_approval_requests_org_created
  ON public.approval_requests (organization_id, created_at DESC);
-- Pending-expiry sweep.
CREATE INDEX IF NOT EXISTS idx_approval_requests_pending_expiry
  ON public.approval_requests (expires_at) WHERE status = 'pending';
-- FK support (execution-gated approvals).
CREATE INDEX IF NOT EXISTS idx_approval_requests_execution
  ON public.approval_requests (workflow_execution_id);

DROP TRIGGER IF EXISTS trg_approval_requests_updated_at ON public.approval_requests;

CREATE TRIGGER trg_approval_requests_updated_at
  BEFORE UPDATE ON public.approval_requests
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.approval_requests ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- approval_logs: immutable approval audit trail (append-only).
-- Rows are never updated or deleted; no updated_at, no write policies.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.approval_logs (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id     uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  approval_request_id uuid NOT NULL REFERENCES public.approval_requests (id) ON DELETE CASCADE,
  actor_user_id       uuid REFERENCES public.users (id) ON DELETE SET NULL,
  action              public.approval_log_action NOT NULL,
  note                text,
  occurred_at         timestamptz NOT NULL DEFAULT now(),
  created_at          timestamptz NOT NULL DEFAULT now()
);

-- Per-request history (oldest first).
CREATE INDEX IF NOT EXISTS idx_approval_logs_request_occurred
  ON public.approval_logs (approval_request_id, occurred_at);
-- Tenant-scoped history listing.
CREATE INDEX IF NOT EXISTS idx_approval_logs_org_occurred
  ON public.approval_logs (organization_id, occurred_at DESC);

ALTER TABLE public.approval_logs ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- briefings: generated founder briefings (org-scoped).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.briefings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  briefing_type   public.briefing_type NOT NULL DEFAULT 'daily',
  title           text NOT NULL,
  summary         text NOT NULL,
  sections        jsonb NOT NULL DEFAULT '[]',
  metadata        jsonb NOT NULL DEFAULT '{}',
  generated_at    timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_briefings_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_briefings_summary_not_blank CHECK (length(btrim(summary)) > 0)
);

-- Latest-by-cadence and org-wide history listings.
CREATE INDEX IF NOT EXISTS idx_briefings_org_type_created
  ON public.briefings (organization_id, briefing_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_briefings_org_created
  ON public.briefings (organization_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_briefings_updated_at ON public.briefings;

CREATE TRIGGER trg_briefings_updated_at
  BEFORE UPDATE ON public.briefings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.briefings ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- growth_metrics: periodized growth/performance rows (org-scoped).
-- Rows are pruned after GROWTH_METRICS_RETENTION_DAYS (36 months) by the
-- retention sweep on recorded_at.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.growth_metrics (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  metric_type     text NOT NULL,
  period_start    timestamptz NOT NULL,
  period_end      timestamptz NOT NULL,
  value           numeric(18, 6) NOT NULL,
  unit            text,
  metadata        jsonb NOT NULL DEFAULT '{}',
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_metrics_type_not_blank CHECK (length(btrim(metric_type)) > 0),
  CONSTRAINT chk_growth_metrics_value_nonneg CHECK (value >= 0),
  CONSTRAINT chk_growth_metrics_period_order CHECK (period_end >= period_start)
);

-- Deterministic upsert target: one row per (org, metric_type, period).
CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_metrics_org_type_period
  ON public.growth_metrics (organization_id, metric_type, period_start, period_end);
-- Series and retention queries.
CREATE INDEX IF NOT EXISTS idx_growth_metrics_org_type_recorded
  ON public.growth_metrics (organization_id, metric_type, recorded_at);
CREATE INDEX IF NOT EXISTS idx_growth_metrics_recorded_retention
  ON public.growth_metrics (recorded_at);

DROP TRIGGER IF EXISTS trg_growth_metrics_updated_at ON public.growth_metrics;

CREATE TRIGGER trg_growth_metrics_updated_at
  BEFORE UPDATE ON public.growth_metrics
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_metrics ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- growth_forecasts: deterministic growth forecasts (org-scoped).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.growth_forecasts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  forecast_type   text NOT NULL,
  horizon_start   timestamptz NOT NULL,
  horizon_end     timestamptz NOT NULL,
  total_value     numeric(18, 6) NOT NULL,
  confidence_low  numeric(18, 6),
  confidence_high numeric(18, 6),
  model_config    jsonb NOT NULL DEFAULT '{}',
  generated_at    timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_growth_forecasts_type_not_blank CHECK (length(btrim(forecast_type)) > 0),
  CONSTRAINT chk_growth_forecasts_total_nonneg CHECK (total_value >= 0),
  CONSTRAINT chk_growth_forecasts_horizon_order CHECK (horizon_end >= horizon_start),
  CONSTRAINT chk_growth_forecasts_confidence_order CHECK (
    confidence_low IS NULL OR confidence_high IS NULL OR confidence_low <= confidence_high
  )
);

-- Latest-by-type and org-wide history listings.
CREATE INDEX IF NOT EXISTS idx_growth_forecasts_org_type_horizon
  ON public.growth_forecasts (organization_id, forecast_type, horizon_start DESC);
CREATE INDEX IF NOT EXISTS idx_growth_forecasts_org_created
  ON public.growth_forecasts (organization_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_growth_forecasts_updated_at ON public.growth_forecasts;

CREATE TRIGGER trg_growth_forecasts_updated_at
  BEFORE UPDATE ON public.growth_forecasts
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.growth_forecasts ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------
-- business_insights: generated business insight rows (org-scoped).
-- source_table / source_row_id is an optional polymorphic reference to the
-- domain row the insight derives from (lead, workflow, metric, etc.).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.business_insights (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  insight_type    public.insight_type NOT NULL,
  severity        public.insight_severity NOT NULL DEFAULT 'info',
  status          public.insight_status NOT NULL DEFAULT 'active',
  title           text NOT NULL,
  summary         text NOT NULL,
  source_table    text,
  source_row_id   uuid,
  metadata        jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_business_insights_title_not_blank CHECK (length(btrim(title)) > 0),
  CONSTRAINT chk_business_insights_summary_not_blank CHECK (length(btrim(summary)) > 0),
  CONSTRAINT chk_business_insights_source_table_not_blank CHECK (
    source_table IS NULL OR length(btrim(source_table)) > 0
  )
);

-- Tenant-scoped lookups.
CREATE INDEX IF NOT EXISTS idx_business_insights_org_status
  ON public.business_insights (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_business_insights_org_type
  ON public.business_insights (organization_id, insight_type);
CREATE INDEX IF NOT EXISTS idx_business_insights_org_created
  ON public.business_insights (organization_id, created_at DESC);
-- Polymorphic source lookup.
CREATE INDEX IF NOT EXISTS idx_business_insights_source
  ON public.business_insights (source_table, source_row_id)
  WHERE source_row_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_business_insights_updated_at ON public.business_insights;

CREATE TRIGGER trg_business_insights_updated_at
  BEFORE UPDATE ON public.business_insights
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.business_insights ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_business_insights_source;
-- DROP INDEX IF EXISTS public.idx_business_insights_org_created;
-- DROP INDEX IF EXISTS public.idx_business_insights_org_type;
-- DROP INDEX IF EXISTS public.idx_business_insights_org_status;
-- DROP INDEX IF EXISTS public.idx_growth_forecasts_org_created;
-- DROP INDEX IF EXISTS public.idx_growth_forecasts_org_type_horizon;
-- DROP INDEX IF EXISTS public.idx_growth_metrics_recorded_retention;
-- DROP INDEX IF EXISTS public.idx_growth_metrics_org_type_recorded;
-- DROP INDEX IF EXISTS public.uq_growth_metrics_org_type_period;
-- DROP INDEX IF EXISTS public.idx_briefings_org_created;
-- DROP INDEX IF EXISTS public.idx_briefings_org_type_created;
-- DROP INDEX IF EXISTS public.idx_approval_logs_org_occurred;
-- DROP INDEX IF EXISTS public.idx_approval_logs_request_occurred;
-- DROP INDEX IF EXISTS public.idx_approval_requests_execution;
-- DROP INDEX IF EXISTS public.idx_approval_requests_pending_expiry;
-- DROP INDEX IF EXISTS public.idx_approval_requests_org_created;
-- DROP INDEX IF EXISTS public.idx_approval_requests_org_approver_status;
-- DROP INDEX IF EXISTS public.idx_approval_requests_org_status;
-- DROP INDEX IF EXISTS public.idx_notifications_created_retention;
-- DROP INDEX IF EXISTS public.idx_notifications_org_created;
-- DROP INDEX IF EXISTS public.idx_notifications_user_unread;
-- DROP INDEX IF EXISTS public.idx_notifications_org_user_read;
-- DROP INDEX IF EXISTS public.idx_agent_state_status_health;
-- DROP INDEX IF EXISTS public.uq_agent_state_org_agent;
-- DROP INDEX IF EXISTS public.idx_agent_runs_created_retention;
-- DROP INDEX IF EXISTS public.idx_agent_runs_org_workflow;
-- DROP INDEX IF EXISTS public.idx_agent_runs_org_created;
-- DROP INDEX IF EXISTS public.idx_agent_runs_org_agent_created;
-- DROP INDEX IF EXISTS public.idx_agent_runs_org_status;
-- DROP INDEX IF EXISTS public.idx_knowledge_items_content_trgm;
-- DROP INDEX IF EXISTS public.idx_knowledge_items_title_trgm;
-- DROP INDEX IF EXISTS public.idx_knowledge_items_source_memory;
-- DROP INDEX IF EXISTS public.idx_knowledge_items_org_created;
-- DROP INDEX IF EXISTS public.idx_knowledge_items_org_category;
-- DROP INDEX IF EXISTS public.idx_ai_memories_content_trgm;
-- DROP INDEX IF EXISTS public.idx_ai_memories_title_trgm;
-- DROP INDEX IF EXISTS public.idx_ai_memories_working_ttl;
-- DROP INDEX IF EXISTS public.idx_ai_memories_source_id;
-- DROP INDEX IF EXISTS public.idx_ai_memories_org_created;
-- DROP INDEX IF EXISTS public.idx_ai_memories_org_type;
-- DROP TABLE IF EXISTS public.business_insights;
-- DROP TABLE IF EXISTS public.growth_forecasts;
-- DROP TABLE IF EXISTS public.growth_metrics;
-- DROP TABLE IF EXISTS public.briefings;
-- DROP TABLE IF EXISTS public.approval_logs;
-- DROP TABLE IF EXISTS public.approval_requests;
-- DROP TABLE IF EXISTS public.notifications;
-- DROP TABLE IF EXISTS public.agent_state;
-- DROP TABLE IF EXISTS public.agent_runs;
-- DROP TABLE IF EXISTS public.knowledge_items;
-- DROP TABLE IF EXISTS public.ai_memories;
-- DROP TYPE IF EXISTS public.insight_status;
-- DROP TYPE IF EXISTS public.insight_severity;
-- DROP TYPE IF EXISTS public.insight_type;
-- DROP TYPE IF EXISTS public.briefing_type;
-- DROP TYPE IF EXISTS public.approval_log_action;
-- DROP TYPE IF EXISTS public.approval_request_status;
-- DROP TYPE IF EXISTS public.notification_type;
-- DROP TYPE IF EXISTS public.agent_health;
-- DROP TYPE IF EXISTS public.agent_state_status;
-- DROP TYPE IF EXISTS public.agent_run_trigger;
-- DROP TYPE IF EXISTS public.agent_run_status;
-- DROP TYPE IF EXISTS public.memory_scope;
-- DROP TYPE IF EXISTS public.memory_type;
-- =====================================================================
