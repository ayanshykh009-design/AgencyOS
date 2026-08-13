"""AgencyOS API entrypoint.

Composes config, middleware, exception handling, telemetry, and routers.
All feature logic must live in the layered packages below.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import (
    AccessLogMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.observability import setup_telemetry
from app.core.rate_limit import register_rate_limit

logger = setup_logging()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup/shutdown lifecycle hooks (with fail-fast config validation)."""
    settings.validate_runtime()
    settings.validate_for_production()
    setup_telemetry(application)
    logger.info("AgencyOS API starting (env=%s, debug=%s)", settings.APP_ENV, settings.APP_DEBUG)
    yield
    logger.info("AgencyOS API shutting down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(
        title=settings.APP_NAME,
        description="Backend for the AI Outreach Agency Operating System.",
        version=settings.APP_VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Middleware order: last added = outermost. RequestID must wrap everything
    # so the request id is available to access logging and error responses.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)
    if settings.SECURITY_HEADERS:
        application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(AccessLogMiddleware)
    application.add_middleware(RequestIDMiddleware)

    register_exception_handlers(application)
    register_rate_limit(application)

    # Mount versioned routers under /api/v1.
    application.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return application


# Module-level app instance — import target for uvicorn and the test client.
app = create_app()
