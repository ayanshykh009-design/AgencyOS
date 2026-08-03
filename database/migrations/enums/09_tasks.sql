-- task_status: lifecycle of a task.
CREATE TYPE public.task_status AS ENUM (
  'todo',
  'in_progress',
  'completed',
  'cancelled'
);

-- task_priority: urgency of a task.
CREATE TYPE public.task_priority AS ENUM (
  'low',
  'medium',
  'high',
  'urgent'
);

-- recurrence_frequency: cadence for repeating tasks.
CREATE TYPE public.recurrence_frequency AS ENUM (
  'daily',
  'weekly',
  'monthly'
);
