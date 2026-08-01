# RLS Policies

Row Level Security policies, one SQL file per table:

- `profiles.sql` — users may read/write their own profile
- `campaigns.sql` — agency members share campaign rows
- `prospects.sql` — scope prospect reads to owning campaign/agency

Every table holding sensitive or tenant-scoped data must ship policies here
before it is used in production.
