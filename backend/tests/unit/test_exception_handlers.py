"""Unit tests: global exception handler contract (error envelope)."""
import json
from typing import Any, cast

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exception_handlers import _validation_error_handler


async def test_validation_handler_returns_structured_errors() -> None:
    """The 422 envelope must carry the structured pydantic error list (dicts),
    not flattened string representations."""
    exc = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", "email"),
                "msg": "Field required",
                "input": {},
            }
        ]
    )
    response = await _validation_error_handler(cast(Any, None), exc)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    body = json.loads(response.body)
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    errors = body["error"]["details"]["errors"]
    assert errors, "expected at least one validation error"
    assert isinstance(errors[0], dict), "validation errors must be structured dicts"
    assert errors[0]["type"] == "missing"
    assert errors[0]["loc"] == ["body", "email"]


async def test_validation_handler_never_leaks_traceback() -> None:
    exc = RequestValidationError([{"type": "value_error", "loc": ("body",), "msg": "bad"}])
    response = await _validation_error_handler(cast(Any, None), exc)
    assert response.status_code == 422
    body = json.loads(response.body)
    assert "traceback" not in json.dumps(body)
