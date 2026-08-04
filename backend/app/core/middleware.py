"""HTTP middleware: request IDs, security headers, and access logging.

Keep middleware generic — no business logic. Middleware is composed in
app/main.py (order matters: last added = outermost).
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings
from app.core.contextvars import request_id_var
from app.core.csp import build_csp_policy

logger = logging.getLogger("agencyos.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a unique X-Request-ID.

    Accepts an inbound id (for distributed tracing) or generates one, then
    echoes it on the response and into the per-request logging context.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply hardened baseline response headers."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.ENABLE_CSP:
            # Restrictive by default; connect-src widens only for explicitly
            # configured origins (see app/core/csp.py).
            response.headers["Content-Security-Policy"] = build_csp_policy()
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Structured access logging: method, path, status, latency, request id."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request %s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
