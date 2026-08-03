-- Tasks: org-scoped to-dos linked to leads and team members.
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
