# Documentation

Central home for AgencyOS documentation.

| Document                  | Purpose                                              |
| ------------------------- | ---------------------------------------------------- |
| `architecture.md`         | System design, layering, data flow, diagram.         |
| `setup.md`                | Full local environment setup guide.                  |
| `database.md`             | Database schema conventions, RLS, migrations.        |
| `security.md`             | Security controls and production must-dos.           |
| `observability.md`        | Logging, request IDs, health probes, OpenTelemetry.  |
| `development.md`          | Day-to-day dev workflow: branch, lint, test, commit. |
| `deployment.md`           | Docker Compose, env matrix, production notes.        |
| `api/`                    | API reference, OpenAPI spec, endpoint docs.          |
| `diagrams/`               | Architecture / sequence diagrams (images, .puml).    |

## Database docs

- `database.md` — V1 schema, conventions, duplicate protection, RLS,
  migration flow, testing.
- `diagrams/database-erd.md` — Mermaid ERD of the 15 core tables.

Keep docs close to the code: when a contract changes, update the matching doc
in the same PR.
