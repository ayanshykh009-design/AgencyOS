"""Global exception handling.

Registers handlers that convert every failure into the standardized error
envelope (see app/core/errors.py). Unknown exceptions are logged (with the
request id) but never leak internals to clients.
"""
import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, ErrorDetail, ErrorResponse

logger = logging.getLogger("agencyos")


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    headers: dict | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details)
    ).model_dump()
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)
    return _error_response(error.status_code, error.code, error.message, error.details)


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    # pydantic v2 already exposes JSON-serializable error dicts; RequestValidationError.json()
    # was removed from current FastAPI, so never call it.
    details = {"errors": error.errors()}
    return _error_response(422, "validation_error", "Request validation failed", details)


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    if error.status_code == 404:
        return _error_response(404, "not_found", "Resource not found")
    return _error_response(error.status_code, "http_error", str(error.detail))


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled exception on %s %s", request.method, request.url.path, exc_info=exc
    )
    return _error_response(500, "internal_error", "An unexpected error occurred")


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to the application."""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
