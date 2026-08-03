-- stage_lifecycle: coarse bucket of a pipeline stage (Kanban column).
CREATE TYPE public.stage_lifecycle AS ENUM (
  'open',
  'won',
  'lost'
);
