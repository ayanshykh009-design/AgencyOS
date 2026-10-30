"""H2 regression tests: outreach writes require ``LEAD_WRITE`` (no VIEWER writes).

Audit finding (R7 Phase 6 readiness): the outreach attempt / follow-up / manual
queue write endpoints were gated by authentication only, so a ``VIEWER`` — a
read-only role everywhere else — could create and mutate lead outreach records.

Policy applied: those records are lead-scoped CRM rows (every create requires a
``lead_id``), so mutating them is a lead write and requires
``Permission.LEAD_WRITE`` — exactly the non-viewer write roles. Reads stay
authenticated-only, matching lead reads.

These tests drive the real application and the real ``require_permission``
dependency. Only the database session and the ``OutreachService`` boundary are
stubbed, because the permission dependency runs *before* the handler: a rejected
request therefore never reaches the service (asserted with a spy), and an
allowed request is proven to reach it with the caller's organization id.

Database-level proof that rejected writes leave no rows behind lives in
``tests/integration/test_outreach_authorization.py`` (runs against PostgreSQL in
CI).
"""

from __future__ import annotations

import ast
import asyncio
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.v1.endpoints import outreach as outreach_module
from app.core.permissions import Permission, has_permission
from app.main import app
from app.models.enums import OutreachChannel, OutreachStatus, UserRole

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
ATTEMPT_ID = uuid.uuid4()
FOLLOW_UP_ID = uuid.uuid4()
TASK_ID = uuid.uuid4()

OUTREACH_PREFIX = "/api/v1/outreach"
WRITE_ROLES = [
    UserRole.OWNER,
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.MEMBER,
    UserRole.SALES_AGENT,
]

CREATE_ATTEMPT = (
    "post",
    f"{OUTREACH_PREFIX}/attempts",
    {"organization_id": str(ORG_ID), "lead_id": str(LEAD_ID), "channel": "email"},
    201,
)
UPDATE_ATTEMPT = (
    "patch",
    f"{OUTREACH_PREFIX}/attempts/{ATTEMPT_ID}",
    {"status": "sent"},
    200,
)
CREATE_FOLLOW_UP = (
    "post",
    f"{OUTREACH_PREFIX}/follow-ups",
    {
        "organization_id": str(ORG_ID),
        "lead_id": str(LEAD_ID),
        "channel": "email",
        "sequence_position": 1,
        "body": "Checking in",
    },
    201,
)
UPDATE_FOLLOW_UP = (
    "patch",
    f"{OUTREACH_PREFIX}/follow-ups/{FOLLOW_UP_ID}",
    {"status": "sent"},
    200,
)
CREATE_MANUAL_TASK = (
    "post",
    f"{OUTREACH_PREFIX}/manual",
    {"organization_id": str(ORG_ID), "lead_id": str(LEAD_ID), "channel": "email"},
    201,
)
UPDATE_MANUAL_TASK = (
    "patch",
    f"{OUTREACH_PREFIX}/manual/{TASK_ID}",
    {"status": "manually_sent"},
    200,
)

WRITE_CASES = [
    pytest.param(*CREATE_ATTEMPT, "create_attempt", id="attempts-create"),
    pytest.param(*UPDATE_ATTEMPT, "update_attempt", id="attempts-update"),
    pytest.param(*CREATE_FOLLOW_UP, "create_follow_up", id="follow-ups-create"),
    pytest.param(*UPDATE_FOLLOW_UP, "update_follow_up", id="follow-ups-update"),
    pytest.param(*CREATE_MANUAL_TASK, "create_manual_task", id="manual-create"),
    pytest.param(*UPDATE_MANUAL_TASK, "update_manual_task", id="manual-update"),
]

READ_CASES = [
    ("get", f"{OUTREACH_PREFIX}/messages"),
    ("get", f"{OUTREACH_PREFIX}/leads/{LEAD_ID}/attempts"),
    ("get", f"{OUTREACH_PREFIX}/leads/{LEAD_ID}/follow-ups"),
    ("get", f"{OUTREACH_PREFIX}/manual"),
]


# -- fakes ------------------------------------------------------------------


class _FakeOutreachService:
    """Records service calls and returns API-shaped rows for the success path."""

    calls: list[tuple[str, uuid.UUID, dict[str, Any]]] = []

    def __init__(self, session: Any) -> None:
        self._session = session

    # reads ---------------------------------------------------------------
    async def list_messages(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append(("list_messages", args[0], {}))
        return []

    async def list_attempts_for_lead(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append(("list_attempts_for_lead", args[0], {}))
        return []

    async def list_follow_ups_for_lead(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append(("list_follow_ups_for_lead", args[0], {}))
        return []

    async def list_manual_tasks(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append(("list_manual_tasks", args[0], {}))
        return []

    # writes --------------------------------------------------------------
    async def create_attempt(self, organization_id: uuid.UUID, data: dict[str, Any]) -> Any:
        self.calls.append(("create_attempt", organization_id, data))
        return _attempt_row(organization_id, data)

    async def update_attempt(
        self, organization_id: uuid.UUID, attempt_id: uuid.UUID, data: dict[str, Any]
    ) -> Any:
        self.calls.append(("update_attempt", organization_id, data))
        return _attempt_row(organization_id, {"lead_id": LEAD_ID, "channel": "email", **data})

    async def create_follow_up(self, organization_id: uuid.UUID, data: dict[str, Any]) -> Any:
        self.calls.append(("create_follow_up", organization_id, data))
        return _follow_up_row(organization_id, data)

    async def update_follow_up(
        self, organization_id: uuid.UUID, follow_up_id: uuid.UUID, data: dict[str, Any]
    ) -> Any:
        self.calls.append(("update_follow_up", organization_id, data))
        return _follow_up_row(
            organization_id,
            {"lead_id": LEAD_ID, "channel": "email", "sequence_position": 1, "body": "x", **data},
        )

    async def create_manual_task(self, organization_id: uuid.UUID, data: dict[str, Any]) -> Any:
        self.calls.append(("create_manual_task", organization_id, data))
        return _manual_task_row(organization_id, data)

    async def update_manual_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID, data: dict[str, Any]
    ) -> Any:
        self.calls.append(("update_manual_task", organization_id, data))
        return _manual_task_row(organization_id, {"lead_id": LEAD_ID, "channel": "email", **data})


def _attempt_row(organization_id: uuid.UUID, data: dict[str, Any]) -> Any:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=ATTEMPT_ID,
        organization_id=organization_id,
        lead_id=data["lead_id"],
        outreach_message_id=None,
        channel=OutreachChannel(data["channel"]),
        status=OutreachStatus(data.get("status", "queued")),
        subject=None,
        body=None,
        scheduled_at=None,
        sent_at=None,
        delivered_at=None,
        external_id=None,
        error_code=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )


def _follow_up_row(organization_id: uuid.UUID, data: dict[str, Any]) -> Any:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=FOLLOW_UP_ID,
        organization_id=organization_id,
        lead_id=data["lead_id"],
        outreach_attempt_id=None,
        channel=OutreachChannel(data["channel"]),
        sequence_position=data["sequence_position"],
        subject=None,
        body=data["body"],
        delay_days=0,
        scheduled_at=None,
        status=OutreachStatus(data.get("status", "queued")),
        sent_at=None,
        created_at=now,
        updated_at=now,
    )


def _manual_task_row(organization_id: uuid.UUID, data: dict[str, Any]) -> Any:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=TASK_ID,
        organization_id=organization_id,
        lead_id=data["lead_id"],
        assigned_user_id=None,
        channel=OutreachChannel(data["channel"]),
        status=OutreachStatus(data.get("status", "queued")),
        priority=0,
        due_at=None,
        subject=None,
        body=None,
        notes=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def outreach_service(monkeypatch: pytest.MonkeyPatch) -> type[_FakeOutreachService]:
    """Patch the endpoint module's service class with a call-recording fake."""
    _FakeOutreachService.calls = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.outreach.OutreachService", _FakeOutreachService
    )
    return _FakeOutreachService


@pytest.fixture
def api_client(outreach_service: type[_FakeOutreachService]) -> Generator[TestClient, None, None]:
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


def _send(client: TestClient, method: str, path: str, payload: dict[str, Any] | None = None):
    if payload is None:
        return getattr(client, method)(path)
    return getattr(client, method)(path, json=payload)


# -- policy / matrix --------------------------------------------------------


def test_lead_write_excludes_viewer_and_grants_the_write_roles() -> None:
    assert not has_permission(UserRole.VIEWER, Permission.LEAD_WRITE)
    for role in WRITE_ROLES:
        assert has_permission(role, Permission.LEAD_WRITE)


# -- rejection paths --------------------------------------------------------


@pytest.mark.parametrize(("method", "path", "payload", "_status", "_service"), WRITE_CASES)
def test_unauthenticated_write_is_rejected(
    api_client: TestClient,
    method: str,
    path: str,
    payload: dict[str, Any],
    _status: int,
    _service: str,
) -> None:
    res = _send(api_client, method, path, payload)
    assert res.status_code == 401, res.text
    assert _FakeOutreachService.calls == []


@pytest.mark.parametrize(("method", "path", "payload", "_status", "_service"), WRITE_CASES)
def test_viewer_write_is_forbidden_and_never_reaches_the_service(
    api_client: TestClient,
    method: str,
    path: str,
    payload: dict[str, Any],
    _status: int,
    _service: str,
) -> None:
    with _authenticated(UserRole.VIEWER):
        res = _send(api_client, method, path, payload)
    assert res.status_code == 403, res.text
    # Rejected before the handler ran: no service call, so no row could be written.
    assert _FakeOutreachService.calls == []


# -- allowed paths ----------------------------------------------------------


@pytest.mark.parametrize("role", WRITE_ROLES)
@pytest.mark.parametrize(("method", "path", "payload", "expected", "service_call"), WRITE_CASES)
def test_authorized_roles_reach_the_handler(
    api_client: TestClient,
    role: UserRole,
    method: str,
    path: str,
    payload: dict[str, Any],
    expected: int,
    service_call: str,
) -> None:
    with _authenticated(role):
        res = _send(api_client, method, path, payload)
    assert res.status_code == expected, res.text
    assert [call[0] for call in _FakeOutreachService.calls] == [service_call]
    assert _FakeOutreachService.calls[0][1] == ORG_ID


@pytest.mark.parametrize(("method", "path"), READ_CASES)
def test_viewer_keeps_read_access(api_client: TestClient, method: str, path: str) -> None:
    with _authenticated(UserRole.VIEWER):
        res = _send(api_client, method, path)
    assert res.status_code == 200, res.text
    assert res.json() == []


# -- message template / lead source policy must not change ------------------


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", f"{OUTREACH_PREFIX}/messages", {"name": "n", "channel": "email", "body": "b"}),
        (
            "patch",
            f"{OUTREACH_PREFIX}/messages/{uuid.uuid4()}",
            {"name": "renamed"},
        ),
        ("delete", f"{OUTREACH_PREFIX}/messages/{uuid.uuid4()}", None),
    ],
)
def test_message_template_writes_stay_admin_only(
    api_client: TestClient, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    with _authenticated(UserRole.MANAGER):
        res = _send(api_client, method, path, payload)
    assert res.status_code == 403, res.text


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/lead-sources", {"name": "Referral"}),
        ("patch", f"/api/v1/lead-sources/{uuid.uuid4()}", {"name": "Renamed"}),
    ],
)
def test_lead_source_writes_stay_admin_only(
    api_client: TestClient, method: str, path: str, payload: dict[str, Any] | None
) -> None:
    with _authenticated(UserRole.MANAGER):
        res = _send(api_client, method, path, payload)
    assert res.status_code == 403, res.text


# -- structural guard: no outreach write route may lose the guard -----------


def _iter_authz_dependencies(route: APIRoute) -> list[Any]:
    """Yield authorization dependency callables (recursively).

    Both guard styles used by the outreach router are recognized:
    ``require_permission`` (``app.core.permissions``) and ``require_role``
    (``app.api.deps``).
    """
    found: list[Any] = []
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        call = dep.call
        name = getattr(call, "__name__", "")
        module = getattr(call, "__module__", "")
        if (module, name) in {
            ("app.core.permissions", "_require"),
            ("app.api.deps", "_require_role"),
        }:
            found.append(call)
        stack.extend(dep.dependencies)
    return found


def _enforced_roles(dependency: Any) -> set[UserRole]:
    """Return the roles that pass a ``require_permission`` dependency."""

    async def _probe() -> set[UserRole]:
        allowed: set[UserRole] = set()
        for role in UserRole:
            user = SimpleNamespace(id=USER_ID, organization_id=ORG_ID, role=role)
            try:
                await dependency(user)
            except HTTPException as exc:
                assert exc.status_code == 403, exc
            else:
                allowed.add(role)
        return allowed

    return asyncio.run(_probe())


def _outreach_routes() -> list[APIRoute]:
    """Routes declared by the outreach router.

    FastAPI 0.143 mounts included routers lazily, so ``app.routes`` holds the
    inclusion node rather than the flattened routes. Inspecting the module
    router directly gives the real ``APIRoute`` objects (with their resolved
    dependencies); ``_assert_routes_are_mounted`` proves they are reachable.
    """
    routes = [route for route in outreach_module.router.routes if isinstance(route, APIRoute)]
    assert routes, "outreach router declares no routes"
    return routes


def _assert_routes_are_mounted(routes: list[APIRoute]) -> None:
    """Every router path must be exposed by the application's OpenAPI schema."""
    documented = set(app.openapi()["paths"])
    for route in routes:
        mounted = f"{OUTREACH_PREFIX}{route.path}"
        assert mounted in documented, f"{mounted} is not mounted by the application"


def test_every_outreach_write_route_enforces_lead_write() -> None:
    unsafe = {"POST", "PUT", "PATCH", "DELETE"}
    routes = _outreach_routes()
    _assert_routes_are_mounted(routes)
    lead_write_routes: set[str] = set()
    admin_only_routes: set[str] = set()
    for route in routes:
        if not (route.methods & unsafe):
            continue
        key = f"{sorted(route.methods)} {route.path}"
        deps = _iter_authz_dependencies(route)
        assert deps, f"{key} has no authorization dependency"
        allowed = set().union(*(_enforced_roles(dep) for dep in deps))
        assert UserRole.VIEWER not in allowed, f"VIEWER can write {key}"
        if route.path.startswith("/messages"):
            admin_only_routes.add(key)
            assert allowed == {UserRole.OWNER, UserRole.ADMIN}, (
                f"{key} allows {sorted(r.value for r in allowed)}"
            )
        else:
            lead_write_routes.add(key)
            assert allowed == set(WRITE_ROLES), (
                f"{key} allows {sorted(r.value for r in allowed)}"
            )

    assert lead_write_routes == {
        f"{sorted(m.upper() for m in methods)} {path}"
        for methods, path in [
            ({"post"}, "/attempts"),
            ({"patch"}, "/attempts/{attempt_id}"),
            ({"post"}, "/follow-ups"),
            ({"patch"}, "/follow-ups/{follow_up_id}"),
            ({"post"}, "/manual"),
            ({"patch"}, "/manual/{task_id}"),
        ]
    }, f"unexpected lead-write route inventory: {sorted(lead_write_routes)}"
    assert admin_only_routes == {
        f"{sorted(m.upper() for m in methods)} {path}"
        for methods, path in [
            ({"post"}, "/messages"),
            ({"patch"}, "/messages/{message_id}"),
            ({"delete"}, "/messages/{message_id}"),
        ]
    }, f"unexpected admin-only route inventory: {sorted(admin_only_routes)}"


def test_read_routes_remain_authenticated_only() -> None:
    routes = _outreach_routes()
    _assert_routes_are_mounted(routes)
    read_routes = 0
    for route in routes:
        if route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        read_routes += 1
        assert _iter_authz_dependencies(route) == [], (
            f"{route.path} unexpectedly requires a permission (VIEWER read access would break)"
        )
    assert read_routes >= 4


def test_outreach_service_has_no_unprotected_api_entry_point() -> None:
    """The service that owns these tables is only instantiated by ``outreach.py``.

    If another router ever wires ``OutreachService`` directly, it would bypass
    the guard verified above; fail loudly instead.
    """
    app_dir = Path(__file__).resolve().parents[2] / "app"
    guarded_router = (app_dir / "api" / "v1" / "endpoints" / "outreach.py").resolve()
    offenders: list[str] = []
    for path in app_dir.rglob("*.py"):
        if path.resolve() == guarded_router:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                name = getattr(target, "id", None) or getattr(target, "attr", None)
                if name == "OutreachService":
                    offenders.append(f"{path.relative_to(app_dir)}:{node.lineno}")
    assert offenders == [], f"OutreachService reachable outside the guarded router: {offenders}"
