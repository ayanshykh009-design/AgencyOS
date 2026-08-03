"""Service-layer unit tests: audit trail delegation and actor resolution."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType
from app.services.activity_service import ActivityService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


def _service() -> ActivityService:
    """Build an activity service whose log repo is stubbed out."""
    service = ActivityService(FakeSession())
    service._logs = MagicMock()
    return service


def _entry(**overrides: object) -> ActivityLog:
    entry = ActivityLog(
        organization_id=ORG_ID,
        event_type=ActivityEventType.LEAD_ASSIGNED,
        occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    entry.id = uuid.uuid4()
    entry.created_at = entry.occurred_at
    entry.metadata_ = {}
    for key, value in overrides.items():
        setattr(entry, key, value)
    return entry


async def test_audit_trail_delegates_filters() -> None:
    service = _service()
    entry = _entry()
    service._logs.audit_list = AsyncMock(return_value=[entry])
    entity_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    since = datetime(2026, 1, 1, tzinfo=UTC)

    result = await service.audit_trail(
        ORG_ID,
        entity_type="lead",
        entity_id=entity_id,
        lead_id=entity_id,
        event_type=ActivityEventType.LEAD_ASSIGNED,
        occurred_after=since,
        limit=25,
        offset=5,
    )

    service._logs.audit_list.assert_awaited_once_with(
        ORG_ID,
        entity_type="lead",
        entity_id=entity_id,
        lead_id=entity_id,
        user_id=None,
        event_type=ActivityEventType.LEAD_ASSIGNED,
        occurred_after=since,
        occurred_before=None,
        limit=25,
        offset=5,
    )
    assert result == [entry]


async def test_audit_trail_defaults() -> None:
    service = _service()
    service._logs.audit_list = AsyncMock(return_value=[])

    result = await service.audit_trail(ORG_ID)

    service._logs.audit_list.assert_awaited_once_with(
        ORG_ID,
        entity_type=None,
        entity_id=None,
        lead_id=None,
        user_id=None,
        event_type=None,
        occurred_after=None,
        occurred_before=None,
        limit=50,
        offset=0,
    )
    assert result == []


def test_actor_metadata_resolved_from_user_relationship() -> None:
    """The endpoint's serializer resolves actor info from the ORM user."""
    from app.api.v1.endpoints import audit

    user = MagicMock()
    user.id = uuid.uuid4()
    user.full_name = "Ada Lovelace"
    user.email = "ada@example.com"
    entry = _entry(user_id=user.id)
    entry.user = user

    read = audit._read(entry)

    assert read.actor_user_id == user.id
    assert read.actor_name == "Ada Lovelace"


def test_actor_metadata_falls_back_to_email() -> None:
    from app.api.v1.endpoints import audit

    user = MagicMock()
    user.id = uuid.uuid4()
    user.full_name = None
    user.email = "ada@example.com"
    entry = _entry(user_id=user.id)
    entry.user = user

    read = audit._read(entry)

    assert read.actor_name == "ada@example.com"


def test_actor_metadata_none_without_user() -> None:
    from app.api.v1.endpoints import audit

    entry = _entry(user_id=None)
    entry.user = None

    read = audit._read(entry)

    assert read.actor_user_id is None
    assert read.actor_name is None
