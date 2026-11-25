# API Documentation

The API is documented by FastAPI itself:

- **OpenAPI JSON:** `GET /api/v1/openapi.json`
- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`

This folder holds the stable, versioned reference:

| Entry                    | Purpose                                     |
| ------------------------ | ------------------------------------------- |
| `openapi.yaml`           | Pinned copy of the generated OpenAPI spec.  |
| `endpoints/`             | Hand-written docs for each endpoint group.  |

When you change an endpoint:

1. Regenerate `docs/api/openapi.yaml` with `python scripts/regen-openapi.py` and commit the diff.
2. Update the matching file in `docs/api/endpoints/`.
3. CI regenerates the snapshot and fails if `docs/api/openapi.yaml` drifts from the live app.
