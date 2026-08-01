# Seeds

Deterministic seed data used to bootstrap environments:

- `01_roles.sql` — application roles/permissions
- `02_demo_agency.sql` — demo agency, users, and sample campaign

Seeds are idempotent (upsert, never duplicate). Run via `make seed`.
