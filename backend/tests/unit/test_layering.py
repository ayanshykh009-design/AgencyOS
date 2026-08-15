"""M10 backend layering + unified error-envelope invariants (static, no DB).

The plan's "production discipline" rules require a strict layering:

    endpoint -> service -> repository -> model

and a single error envelope (``app.core.errors.AppError``) registered with the
FastAPI app. These tests statically verify the boundaries are not violated and
that failures are funnelled through the envelope rather than leaking raw
tracebacks.
"""

from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
ENDPOINTS = APP / "api" / "v1" / "endpoints"
SERVICES = APP / "services"


def _py_files(folder: pathlib.Path):
    return [p for p in folder.rglob("*.py") if p.name != "__init__.py"]


# Endpoint handlers must never touch the database driver or raw SQL directly.
ENDPOINT_FORBIDDEN = (
    "engine.execute",
    "cursor.execute",
    "text(",
    "psycopg2",
    "asyncpg",
)

# Service layer may use the ORM session (session.execute(select(...))) but must
# never drop to driver-level execution (engine/cursor) or raw driver imports.
SERVICE_FORBIDDEN = (
    "engine.execute",
    "cursor.execute",
)


def test_endpoints_never_execute_raw_sql():
    offenders = []
    for f in _py_files(ENDPOINTS):
        src = f.read_text(encoding="utf-8")
        for tok in ENDPOINT_FORBIDDEN:
            if tok in src:
                offenders.append(f"{f.name}: contains {tok!r}")
    assert not offenders, "Endpoint handlers must delegate to services:\n" + "\n".join(offenders)


def test_endpoints_are_real_routers():
    broken = []
    for f in _py_files(ENDPOINTS):
        src = f.read_text(encoding="utf-8")
        has_router = "APIRouter(" in src
        has_handler = "@router." in src or "@app." in src
        if not (has_router and has_handler):
            broken.append(f.name)
    assert not broken, "Endpoint module has no route handlers:\n" + "\n".join(broken)


def test_services_never_use_driver_level_sql():
    offenders = []
    for f in _py_files(SERVICES):
        src = f.read_text(encoding="utf-8")
        for tok in SERVICE_FORBIDDEN:
            if tok in src:
                offenders.append(f"{f.name}: contains {tok!r}")
    assert not offenders, "Service layer must use ORM/repositories:\n" + "\n".join(offenders)


def test_services_do_not_import_endpoint_layer():
    # Dependency direction: endpoints depend on services, never the reverse.
    offenders = []
    for f in _py_files(SERVICES):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("app.api"):
                    offenders.append(f"{f.name}: imports {node.module}")
    assert not offenders, "Service imports the endpoint layer:\n" + "\n".join(offenders)


def test_error_envelope_registered():
    from fastapi import FastAPI

    from app.core import errors
    from app.main import app

    assert isinstance(app, FastAPI)
    # The unified envelope exception is registered as a handler.
    assert errors.AppError in app.exception_handlers


def test_app_error_is_envelope_shaped():
    from app.core import errors

    exc = errors.AppError(status_code=400, code="test.code", message="boom")
    body = exc.to_response()
    assert body.error.code == "test.code"
    assert body.error.message == "boom"
    assert isinstance(body.error, errors.ErrorDetail)
