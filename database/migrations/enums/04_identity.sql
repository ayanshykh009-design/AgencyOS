-- user_role: access level of a user within their organization.
CREATE TYPE public.user_role AS ENUM (
  'owner',
  'admin',
  'member',
  'viewer'
);
