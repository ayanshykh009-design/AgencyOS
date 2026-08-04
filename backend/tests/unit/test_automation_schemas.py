"""Schema contract tests: automation Pydantic models."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models.enums import ExecutionStatus, WorkflowStatus, WorkflowTriggerType
from app.schemas.credential import CredentialCreate, CredentialRead
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.schemas.workflow_event import WorkflowEventCreate
from app.schemas.workflow_execution import WorkflowExecutionCreate
from app.schemas.workflow_trigger import WorkflowTriggerCreate

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")


def test_workflow_create_validates_execution_mode() -> None:
    with pytest.raises(ValidationError):
        WorkflowCreate(
            organization_id=ORG_ID, name="x", execution_mode="docker"
        )


def test_workflow_update_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        WorkflowUpdate(name="")


def test_workflow_execution_retry_backoff_pattern() -> None:
    with pytest.raises(ValidationError):
        WorkflowExecutionCreate(
            organization_id=ORG_ID,
            workflow_id=WORKFLOW_ID,
            retry_backoff="linear",
        )


def test_workflow_execution_max_attempts_bounds() -> None:
    with pytest.raises(ValidationError):
        WorkflowExecutionCreate(
            organization_id=ORG_ID, workflow_id=WORKFLOW_ID, max_attempts=0
        )


def test_workflow_execution_defaults() -> None:
    data = WorkflowExecutionCreate(organization_id=ORG_ID, workflow_id=WORKFLOW_ID)
    assert data.max_attempts == 3
    assert data.retry_delay_seconds == 60
    assert data.retry_backoff == "exponential"
    assert data.input == {}


def test_trigger_event_type_min_length() -> None:
    with pytest.raises(ValidationError):
        WorkflowTriggerCreate(
            organization_id=ORG_ID,
            workflow_id=WORKFLOW_ID,
            name="t",
            trigger_type=WorkflowTriggerType.EVENT,
            event_type="",
        )


def test_event_create_default_payload() -> None:
    data = WorkflowEventCreate(organization_id=ORG_ID, event_type="lead_created")
    assert data.payload == {}


def test_credential_create_requires_encrypted_value() -> None:
    with pytest.raises(ValidationError):
        CredentialCreate(organization_id=ORG_ID, name="k", credential_type="api_key")


def test_credential_read_never_exposes_encrypted_value() -> None:
    # Wire contract: CredentialRead has no encrypted_value field at all.
    assert "encrypted_value" not in CredentialRead.model_fields
    assert "value_preview" in CredentialRead.model_fields


def test_execution_status_enum_has_expected_values() -> None:
    assert ExecutionStatus.TIMED_OUT.value == "timed_out"
    assert WorkflowStatus.ACTIVE.value == "active"
