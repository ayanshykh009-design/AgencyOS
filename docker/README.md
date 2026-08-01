# Docker

Container definitions for every service. Dockerfiles are referenced by
`docker-compose.yml` at the repo root (build context = repo root).

| Folder        | Container                                     |
| ------------- | --------------------------------------------- |
| `backend/`    | FastAPI image (python:3.12-slim).             |
| `frontend/`   | Next.js dev image (node:20-alpine).           |
| `n8n/`        | n8n automation image (extends official).      |
| `postgres/`   | DB init scripts for the local Postgres.       |

Production images should be multi-stage (build → slim runtime); the current
files are development-oriented by default.
