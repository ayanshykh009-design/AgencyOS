"""API tests: invalid automation query enums return 422, never 500."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.enums import UserRole

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")


@pytest.fixture(autouse=True)
def _authenticated_owner() -> None:
    async def _stub_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _stub_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), organization_id=ORG_ID, role=UserRole.OWNER
    )
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def _assert_validation_error(res) -> None:
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["errors"]


def test_invalid_trigger_type_query_is_validation_error(client) -> None:
    res = client.get("/api/v1/workflow-triggers", params={"trigger_type": "bogus"})
    _assert_validation_error(res)


def test_invalid_nested_trigger_type_query_is_validation_error(client) -> None:
    res = client.get(f"/api/v1/workflows/{WORKFLOW_ID}/triggers", params={"trigger_type": "bogus"})
    _assert_validation_error(res)


def test_invalid_execution_status_query_is_validation_error(client) -> None:
    res = client.get(f"/api/v1/workflows/{WORKFLOW_ID}/executions", params={"status": "bogus"})
    _assert_validation_error(res)
