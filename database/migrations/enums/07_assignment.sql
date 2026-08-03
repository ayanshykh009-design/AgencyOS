-- assignment_strategy: how leads are auto-assigned to team members.
CREATE TYPE public.assignment_strategy AS ENUM (
  'manual',
  'round_robin',
  'rules'
);

-- assignment_method: how a specific ownership change was made.
CREATE TYPE public.assignment_method AS ENUM (
  'manual',
  'round_robin',
  'rules',
  'bulk',
  'unassigned'
);
