-- user_role: access level of a user within their organization.
-- Ordered least -> most privileged: viewer < member ~ sales_agent < manager < admin < owner.
CREATE TYPE public.user_role AS ENUM (
  'owner',
  'admin',
  'manager',
  'member',
  'sales_agent',
  'viewer'
);
