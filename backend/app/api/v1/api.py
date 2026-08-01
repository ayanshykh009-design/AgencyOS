"""v1 router aggregation.

Every feature router is included here exactly once, then mounted in
app/main.py under the API_V1_PREFIX.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, health

api_router = APIRouter()

# Operational endpoints.
api_router.include_router(health.router, prefix="/health", tags=["health"])

# Feature endpoints (placeholder stubs; wire services when implemented).
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
