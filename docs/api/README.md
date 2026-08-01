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

1. Update `docs/api/openapi.yaml` (or regenerate and commit the diff).
2. Update the matching file in `docs/api/endpoints/`.
