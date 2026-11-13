"""API-level RBAC tests for the pipeline stage-move endpoint.

``POST /api/v1/pipeline/leads/{lead_id}/stage`` requires
``Permission.LEAD_WRITE``: every non-viewer role passes; a ``VIEWER`` is
forbidden *before the handler runs*, so no pipeline state, win/loss
timestamp, or mutation activity record can be produced by a denied request
(asserted with a call-recording spy on both services).

Cross-tenant lead/stage/close-reason resolution is enforced inside the
organization-scoped services (``LeadService.get`` and ``PipelineService.move``
receive the caller's organization id — asserted here) and is proven at the
database level by the PostgreSQL integration suite in CI.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.core.permissions import Permission, has_permission
from app.main import app
from app.models.enums import LeadStatus, UserRole

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
STAGE_ID = uuid.uuid4()
CLOSE_REASON_ID = uuid.uuid4()
PIPELINE_PREFIX = "/api/v1/pipeline"


def _lead_row() -> Any:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=LEAD_ID,
        organization_id=ORG_ID,
        first_name="Ada",
        last_name="Lovelace",
        company=None,
        position=None,
        location=None,
        linkedin_url=None,
        email="ada@example.com",
        phone=None,
        whatsapp=None,
        website=None,
        notes=None,
        status=LeadStatus.NEW,
        score=0,
        deal_value=Decimal("0"),
        lead_source_id=None,
        owner_user_id=None,
        stage_id=STAGE_ID,
        close_reason_id=None,
        won_at=None,
        lost_at=None,
        email_normalized="ada@example.com",
        phone_normalized=None,
        website_domain=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


class _FakeLeadService:
    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, session: Any) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID, lead_id: uuid.UUID) -> Any:
        self.calls.append(
            ("get", {"organization_id": str(organization_id), "lead_id": str(lead_id)})
        )
        return _lead_row()


class _FakePipelineService:
    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, session: Any) -> None:
        self._session = session

    async def move(
        self,
        organization_id: uuid.UUID,
        actor: Any,
        lead: Any,
        *,
        stage_id: uuid.UUID,
        close_reason_id: uuid.UUID | None,
    ) -> Any:
        self.calls.append(
            (
                "move",
                {
                    "organization_id": str(organization_id),
                    "actor_id": str(actor.id),
                    "stage_id": str(stage_id),
                    "close_reason_id": str(close_reason_id) if close_reason_id else None,
                },
            )
        )
        return lead


@pytest.fixture
def pipeline_fakes(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[type[_FakeLeadService], type[_FakePipelineService]]:
    _FakeLeadService.calls = []
    _FakePipelineService.calls = []
    monkeypatch.setattr("app.api.v1.endpoints.pipeline.LeadService", _FakeLeadService)
    monkeypatch.setattr("app.api.v1.endpoints.pipeline.PipelineService", _FakePipelineService)
    return _FakeLeadService, _FakePipelineService


@pytest.fixture
def api_client(
    pipeline_fakes: tuple[type[_FakeLeadService], type[_FakePipelineService]],
) -> Generator[TestClient, None, None]:
    async def _stub_db() -> Any:
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = _stub_db
    try:
        with TestClient(app, base_url="http://localhost") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@contextmanager
def _authenticated(role: UserRole) -> Generator[None, None, None]:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=USER_ID, organization_id=ORG_ID, role=role
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _stage_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"stage_id": str(STAGE_ID)}
    payload.update(overrides)
    return payload


# -- policy / matrix --------------------------------------------------------


def test_stage_move_permission_matrix() -> None:
    for role in (
        UserRole.OWNER,
        UserRole.ADMIN,
        UserRole.MANAGER,
        UserRole.MEMBER,
        UserRole.SALES_AGENT,
    ):
        assert has_permission(role, Permission.LEAD_WRITE)
    assert not has_permission(UserRole.VIEWER, Permission.LEAD_WRITE)


# -- rejection paths --------------------------------------------------------


def test_unauthenticated_stage_move_is_rejected(api_client: TestClient) -> None:
    res = api_client.post(f"{PIPELINE_PREFIX}/leads/{LEAD_ID}/stage", json=_stage_payload())
    assert res.status_code == 401, res.text
    assert _FakeLeadService.calls == []
    assert _FakePipelineService.calls == []


def test_viewer_stage_move_is_forbidden_and_never_reaches_the_service(
    api_client: TestClient,
) -> None:
    with _authenticated(UserRole.VIEWER):
        res = api_client.post(f"{PIPELINE_PREFIX}/leads/{LEAD_ID}/stage", json=_stage_payload())
    assert res.status_code == 403, res.text
    assert _FakeLeadService.calls == []
    assert _FakePipelineService.calls == []


# -- allowed paths ----------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER, UserRole.MEMBER, UserRole.SALES_AGENT],
)
def test_write_roles_can_move_a_stage(api_client: TestClient, role: UserRole) -> None:
    with _authenticated(role):
        res = api_client.post(f"{PIPELINE_PREFIX}/leads/{LEAD_ID}/stage", json=_stage_payload())
    assert res.status_code == 200, res.text
    (get_call,) = _FakeLeadService.calls
    (move_call,) = _FakePipelineService.calls
    # Organization scope comes from the authenticated caller, never the client.
    assert get_call[1]["organization_id"] == str(ORG_ID)
    assert get_call[1]["lead_id"] == str(LEAD_ID)
    assert move_call[1]["organization_id"] == str(ORG_ID)
    assert move_call[1]["stage_id"] == str(STAGE_ID)


def test_close_reason_is_forwarded_to_the_service(api_client: TestClient) -> None:
    with _authenticated(UserRole.OWNER):
        res = api_client.post(
            f"{PIPELINE_PREFIX}/leads/{LEAD_ID}/stage",
            json=_stage_payload(close_reason_id=str(CLOSE_REASON_ID)),
        )
    assert res.status_code == 200, res.text
    (move_call,) = _FakePipelineService.calls
    assert move_call[1]["close_reason_id"] == str(CLOSE_REASON_ID)
