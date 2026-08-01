"""AgencyOS API entrypoint.

This module only wires the application together (config, middleware, routers).
All feature logic must live in the layered packages below.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import setup_logging

logger = setup_logging()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(
        title=settings.APP_NAME,
        description="Backend for the AI Outreach Agency Operating System.",
        version=settings.APP_VERSION,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS: allow the Next.js frontend (and other configured origins).
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount versioned routers under /api/v1.
    application.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @application.on_event("startup")
    async def on_startup() -> None:
        logger.info(
            "AgencyOS API starting (env=%s, debug=%s)", settings.APP_ENV, settings.APP_DEBUG
        )

    @application.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("AgencyOS API shutting down")

    return application


# Module-level app instance — import target for uvicorn and the test client.
app = create_app()
