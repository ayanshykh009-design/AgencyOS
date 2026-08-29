-- =====================================================================
-- 0011_tasks.sql
-- Tasks: org-scoped to-dos linked to leads and team members.
--
--   * task_status:           todo | in_progress | completed | cancelled
--   * task_priority:         low | medium | high | urgent
--   * recurrence_frequency:  daily | weekly | monthly
--   * tasks: title/description, due/reminder scheduling, optional
--     recurrence, completion bookkeeping (completed_at).
--   * activity_event_type grows task_created/updated/completed/deleted so
--     the task trail is fully auditable via activity_logs.
--
-- Completing a recurring task reopens it (the row is the task template and
-- the schedule is advanced in the service layer). All statements are
-- idempotent so CI can re-apply them against a live database.
-- =====================================================================

-- ---------------------------------------------------------------------
-- enums
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.agencyos_create_enum(p_name text, p_values text[])
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_expr text;
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' AND t.typname = p_name
  ) THEN
    SELECT string_agg(quote_literal(v), ', ' ORDER BY ord)
      INTO v_expr
      FROM unnest(p_values) WITH ORDINALITY AS x(v, ord);
    EXECUTE format('CREATE TYPE public.%I AS ENUM (%s)', p_name, v_expr);
  END IF;
END;
$$;

SELECT public.agencyos_create_enum(
  'task_status', ARRAY['todo', 'in_progress', 'completed', 'cancelled']
);
SELECT public.agencyos_create_enum(
  'task_priority', ARRAY['low', 'medium', 'high', 'urgent']
);
SELECT public.agencyos_create_enum(
  'recurrence_frequency', ARRAY['daily', 'weekly', 'monthly']
);

DROP FUNCTION public.agencyos_create_enum(text, text[]);

-- Extend the closed activity event set with task lifecycle events.
DO $$
DECLARE
  v_label text;
BEGIN
  FOREACH v_label IN ARRAY ARRAY['task_created', 'task_updated', 'task_completed', 'task_deleted']
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_enum e
      JOIN pg_type t ON t.oid = e.enumtypid
      JOIN pg_namespace n ON n.oid = t.typnamespace
      WHERE n.nspname = 'public'
        AND t.typname = 'activity_event_type'
        AND e.enumlabel = v_label
    ) THEN
      EXECUTE format('ALTER TYPE public.activity_event_type ADD VALUE IF NOT EXISTS %L', v_label);
    END IF;
  END LOOP;
END;
$$;

-- ---------------------------------------------------------------------
-- tasks
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tasks (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      uuid NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  lead_id              uuid REFERENCES public.leads (id) ON DELETE SET NULL,
  assignee_user_id     uuid REFERENCES public.users (id) ON DELETE SET NULL,
  created_by_user_id   uuid REFERENCES public.users (id) ON DELETE SET NULL,
  title                text NOT NULL CHECK (length(btrim(title)) > 0),
  description          text,
  status               public.task_status NOT NULL DEFAULT 'todo',
  priority             public.task_priority NOT NULL DEFAULT 'medium',
  due_at               timestamptz,
  reminder_at          timestamptz,
  completed_at         timestamptz,
  recurrence_frequency public.recurrence_frequency,
  recurrence_interval  integer CHECK (recurrence_interval >= 1),
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT chk_tasks_completed_at_consistent
    CHECK (completed_at IS NULL OR status = 'completed'),
  CONSTRAINT chk_tasks_recurrence_paired
    CHECK ((recurrence_frequency IS NULL) = (recurrence_interval IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_tasks_org_due ON public.tasks (organization_id, due_at);
CREATE INDEX IF NOT EXISTS idx_tasks_org_status ON public.tasks (organization_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_org_lead ON public.tasks (organization_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_tasks_org_assignee ON public.tasks (organization_id, assignee_user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_org_reminder ON public.tasks (organization_id, reminder_at);

DROP TRIGGER IF EXISTS trg_tasks_updated_at ON public.tasks;

CREATE TRIGGER trg_tasks_updated_at
  BEFORE UPDATE ON public.tasks
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- ROLLBACK
-- =====================================================================
-- DROP TABLE IF EXISTS public.tasks;
-- DROP TYPE IF EXISTS public.recurrence_frequency;
-- DROP TYPE IF EXISTS public.task_priority;
-- DROP TYPE IF EXISTS public.task_status;
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'task_deleted';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'task_completed';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'task_updated';
-- ALTER TYPE public.activity_event_type DROP VALUE IF EXISTS 'task_created';
-- =====================================================================
