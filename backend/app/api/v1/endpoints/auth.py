"""Authentication endpoints (placeholder).

Intended routes: register, login, refresh, logout, me.

Business logic is intentionally NOT implemented yet. When building, follow the
layered flow:

    this router  ->  app/services/auth_service.py  ->  app/repositories/...

and use the schemas in app/schemas/auth.py as the request/response contract.
"""
from fastapi import APIRouter

router = APIRouter()

# Example shape (uncomment when auth is implemented):
#
# @router.post("/register", response_model=schemas.AuthResponse)
# async def register(body: schemas.RegisterRequest, db: DbSession) -> schemas.AuthResponse:
#     return await auth_service.register(db, body)
