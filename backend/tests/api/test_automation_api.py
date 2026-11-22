"""API tests: automation routes are registered and auth-guarded.

Full CRUD needs a live DB + authenticated user (covered by integration), so
here we verify the routes exist and unauthenticated requests get a structured
401 without touching the database.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.enums import ExecutionStatus
from app.schemas.workflow_execution import WorkflowExecutionRead
from app.services.execution_adapter import adapter_error_payload
from app.services.n8n_client import N8nHttpError

WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
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
    _expect_401(client, "get", f"/api/v1/workflow-executions/{EXECUTION_ID}/events")
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


def test_active_route_is_declared_before_dynamic_workflow_route() -> None:
    """B6-F-01: the literal /active path must not be shadowed by /{workflow_id}."""
    from app.api.v1.endpoints.workflows import router as workflows_router

    paths = [getattr(route, "path", "") for route in workflows_router.routes]
    assert "/active" in paths
    assert "/{workflow_id}" in paths
    assert paths.index("/active") < paths.index("/{workflow_id}")


def test_active_literal_path_resolves_before_uuid_validation(client) -> None:
    """B6-F-01: /active resolves to the literal route (401), not a 422 UUID error."""
    _expect_401(client, "get", "/api/v1/workflows/active")


def test_execution_read_schema_never_exposes_raw_provider_body() -> None:
    """B6-R1-03: provider response text must not survive into the API payload."""
    raw_body = "access_token=abc123 internal-host=n8n.internal"
    now = datetime.now(UTC)
    read = WorkflowExecutionRead(
        id=EXECUTION_ID,
        organization_id=ORG_ID,
        workflow_id=WORKFLOW_ID,
        trigger_id=None,
        status=ExecutionStatus.QUEUED,
        input={},
        max_attempts=3,
        retry_delay_seconds=60,
        retry_backoff="exponential",
        attempts=0,
        created_at=now,
        updated_at=now,
        error=adapter_error_payload(
            N8nHttpError(status_code=502, body=raw_body, url="/webhook/x")
        ),
    )

    serialized = str(read.model_dump())
    assert "access_token=abc123" not in serialized
    assert "n8n.internal" not in serialized
    assert "<redacted provider response>" in serialized
