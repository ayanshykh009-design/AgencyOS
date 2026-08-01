"""Health-check response schemas."""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Payload returned by liveness probes."""

    status: str
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Payload returned by readiness probes."""

    status: str
    service: str
    db: bool
