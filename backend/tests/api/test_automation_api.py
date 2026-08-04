"""API tests: automation routes are registered and auth-guarded.

Full CRUD needs a live DB + authenticated user (covered by integration), so
here we verify the routes exist and unauthenticated requests get a structured
401 without touching the database.
"""
from __future__ import annotations

import uuid

WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
TRIGGER_ID = uuid.UUID("00000000-0000-0000-0000-000000000701")
EXECUTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000601")
EVENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000801")
CREDENTIAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000901")


def _expect_401(client, method: str, url: str, **kwargs) -> None:
    res = getattr(client, method)(url, **kwargs)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "auth.missing_token"


def test_workflows_require_auth(client) -> None:
    _expect_401(client, "get", "/api/v1/workflows")
    _expect_401(client, "post", "/api/v1/workflows", json={})
    _expect_401(client, "get", f"/api/v1/workflows/{WORKFLOW_ID}")
    _expect_401(client, "patch", f"/api/v1/workflows/{WORKFLOW_ID}", json={})
    _expect_401(client, "post", f"/api/v1/workflows/{WORKFLOW_ID}/activate")
    _expect_401(client, "delete", f"/api/v1/workflows/{WORKFLOW_ID}")


def test_workflow_triggers_require_auth(client) -> None:
    _expect_401(client, "get", "/api/v1/workflow-triggers")
    _expect_401(client, "post", "/api/v1/workflow-triggers", json={})
    _expect_401(client, "get", f"/api/v1/workflow-triggers/{TRIGGER_ID}")
    _expect_401(client, "post", f"/api/v1/workflow-triggers/{TRIGGER_ID}/enable")


def test_workflow_executions_require_auth(client) -> None:
    _expect_401(client, "get", "/api/v1/workflow-executions")
    _expect_401(client, "post", "/api/v1/workflow-executions", json={})
    _expect_401(client, "get", f"/api/v1/workflow-executions/{EXECUTION_ID}")
    _expect_401(client, "post", f"/api/v1/workflow-executions/{EXECUTION_ID}/start")
    _expect_401(client, "post", f"/api/v1/workflow-executions/{EXECUTION_ID}/cancel")


def test_workflow_events_require_auth(client) -> None:
    _expect_401(client, "get", "/api/v1/workflow-events")
    _expect_401(client, "post", "/api/v1/workflow-events", json={})


def test_credentials_require_auth(client) -> None:
    _expect_401(client, "get", "/api/v1/credentials")
    _expect_401(client, "post", "/api/v1/credentials", json={})
    _expect_401(client, "get", f"/api/v1/credentials/{CREDENTIAL_ID}")
    _expect_401(client, "delete", f"/api/v1/credentials/{CREDENTIAL_ID}")
    _expect_401(client, "post", f"/api/v1/credentials/{CREDENTIAL_ID}/rotate")


def test_credentials_never_return_encrypted_value_contract() -> None:
    # Wire guard: the credentials list route must not expose encrypted_value.
    from app.schemas.credential import CredentialRead

    assert "encrypted_value" not in CredentialRead.model_fields
