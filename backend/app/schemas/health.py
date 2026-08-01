"""Health-check response schemas."""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Payload returned by the health endpoint."""

    status: str
    service: str
