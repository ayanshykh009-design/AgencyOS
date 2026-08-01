# Migrations

Versioned, append-only schema migrations. Naming:

`NNNN_description.sql`   (e.g. `0001_initial_schema.sql`)

Rules:

- One migration per file, applied in ascending numeric order.
- Each migration must be reversible on paper (write a rollback comment block).
- Never edit an applied migration — add a new one instead.

For backend-managed migrations, `backend/alembic/` serves the same role; keep
the two in sync or standardize on one source of truth per table.
