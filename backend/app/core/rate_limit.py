"""Rate limiting.

Uses slowapi. Storage:
- in-memory by default (single instance / dev),
- Redis when REDIS_URL is set (required for multi-instance deployments).

Apply per-endpoint limits with `@limiter.limit(settings.RATE_LIMIT_STRICT)`
(e.g. on auth endpoints). Register via register_rate_limit(app).
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.errors import ErrorDetail, ErrorResponse

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL or "memory://",
    headers_enabled=True,
    default_limits=[],  # apply explicit @limiter.limit() per sensitive route
)


async def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code="rate_limited", message="Rate limit exceeded, retry later")
    ).model_dump()
    return JSONResponse(status_code=429, content=body)


def register_rate_limit(app: FastAPI) -> None:
    """Wire the limiter and its error handler into the app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
