"""Health / liveness endpoints.

Used by load balancers, orchestrators, and CI to verify the service is up.
No business logic here.
"""
from fastapi import APIRouter, status

router = APIRouter()


@router.get(
    "/health",
    summary="Liveness probe",
    status_code=status.HTTP_200_OK,
    tags=["health"],
)
async def health() -> dict[str, str]:
    """Return service status for infrastructure monitoring."""
    return {"status": "ok", "service": "agencyos-api"}
