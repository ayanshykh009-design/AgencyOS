-- invite_status: lifecycle of a team invite.
CREATE TYPE public.invite_status AS ENUM (
  'pending',
  'accepted',
  'revoked',
  'expired'
);
