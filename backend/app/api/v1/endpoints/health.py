"""Health endpoints: liveness and readiness probes.

- `/health/live` — process alive; orchestrators use this to restart dead pods.
- `/health/ready` — dependencies (database) reachable; traffic routers use this
  to stop routing to an instance that cannot serve requests.

No business logic here.
"""
from fastapi import APIRouter, status

from app.core.config import settings
from app.core.database import check_database_connection
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get(
    "/live",
    response_model=HealthResponse,
    summary="Liveness probe",
    status_code=status.HTTP_200_OK,
    tags=["health"],
)
async def liveness() -> HealthResponse:
    """Return service status for infrastructure monitoring."""
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    status_code=status.HTTP_200_OK,
    tags=["health"],
)
async def readiness() -> ReadinessResponse:
    """Report whether dependencies (e.g. database) are reachable."""
    db_ok = await check_database_connection()
    return ReadinessResponse(
        status="ok" if db_ok else "degraded",
        service=settings.APP_NAME,
        db=db_ok,
    )


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health alias (liveness)",
    tags=["health"],
    include_in_schema=False,
)
async def health_alias() -> HealthResponse:
    """Backward-compatible alias for /health."""
    return await liveness()
