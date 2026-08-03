"""Service-layer unit tests: note CRUD and activity trail."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType, UserRole
from app.models.lead import Lead
from app.models.note import Note
from app.models.user import User
from app.services.note_service import NoteService

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


def _make_note(**overrides: object) -> Note:
    note = Note(
        organization_id=ORG_ID,
        lead_id=uuid.uuid4(),
        body="Initial note",
        pinned=False,
    )
    note.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(note, key, value)
    return note


def _make_lead(**overrides: object) -> Lead:
    lead = Lead(organization_id=ORG_ID, email="prospect@example.com")
    lead.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(lead, key, value)
    return lead


def _make_user(**overrides: object) -> User:
    user = User(
        organization_id=ORG_ID,
        email="member@example.com",
        full_name="Member",
        role=UserRole.MEMBER,
        password_hash=None,
    )
    user.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _service(session: FakeSession, **repos: object) -> NoteService:
    service = NoteService(session)
    service._notes = MagicMock()
    service._leads = MagicMock()
    service._activity = MagicMock()
    for name, fake in repos.items():
        setattr(service, name, fake)
    return service


def _wire_add(service: NoteService, session: FakeSession) -> None:
    service._notes.add = MagicMock(side_effect=session.add)
    service._activity.add = MagicMock(side_effect=session.add)


@pytest.mark.asyncio
async def test_create_note_persists_and_emits_event() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    lead = _make_lead()
    service._leads.get_or_404 = AsyncMock(return_value=lead)

    note = await service.create(
        ORG_ID, _make_user(), lead_id=lead.id, body="  Call scheduled  ", pinned=True
    )

    assert note.body == "Call scheduled"
    assert note.pinned is True
    assert note.lead_id == lead.id
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.NOTE_CREATED
    assert entry.lead_id == lead.id
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_note_rejects_blank_body() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    lead = _make_lead()
    service._leads.get_or_404 = AsyncMock(return_value=lead)

    with pytest.raises(AppError) as exc_info:
        await service.create(ORG_ID, _make_user(), lead_id=lead.id, body="   ")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "note.body_required"


@pytest.mark.asyncio
async def test_create_note_validates_lead_exists() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    service._leads.get_or_404 = AsyncMock(
        side_effect=AppError("lead.not_found", "Lead not found", 404)
    )

    with pytest.raises(AppError) as exc_info:
        await service.create(ORG_ID, _make_user(), lead_id=uuid.uuid4(), body="hi")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "lead.not_found"


@pytest.mark.asyncio
async def test_update_note_changes_fields_and_emits_event() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    note = _make_note()
    service._notes.get_or_404 = AsyncMock(return_value=note)

    result = await service.update(
        ORG_ID, _make_user(), note.id, body="Updated", pinned=True
    )

    assert result.body == "Updated"
    assert result.pinned is True
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.NOTE_UPDATED
    assert session.committed is True


@pytest.mark.asyncio
async def test_delete_note_removes_and_emits_event() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    note = _make_note()
    service._notes.get_or_404 = AsyncMock(return_value=note)
    service._notes.delete = AsyncMock()

    await service.delete(ORG_ID, _make_user(), note.id)

    service._notes.delete.assert_awaited_once_with(note)
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.NOTE_DELETED
    assert session.committed is True


@pytest.mark.asyncio
async def test_list_by_lead_validates_lead_and_delegates() -> None:
    session = FakeSession()
    service = _service(session)
    lead = _make_lead()
    note = _make_note(lead_id=lead.id)
    service._leads.get_or_404 = AsyncMock(return_value=lead)
    service._notes.list_by_lead = AsyncMock(return_value=[note])

    result = await service.list_by_lead(ORG_ID, lead.id)

    assert result == [note]
    service._leads.get_or_404.assert_awaited_once_with(ORG_ID, lead.id)
    service._notes.list_by_lead.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_unknown_note_raises_404() -> None:
    session = FakeSession()
    service = _service(session)
    service._notes.get_or_404 = AsyncMock(
        side_effect=AppError("note.not_found", "Note not found", 404)
    )

    with pytest.raises(AppError) as exc_info:
        await service.get(ORG_ID, uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "note.not_found"
