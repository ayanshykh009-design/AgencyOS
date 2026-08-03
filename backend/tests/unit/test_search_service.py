"""Service-layer unit tests: unified search across leads, tasks, and notes."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import LeadStatus, TaskPriority, TaskStatus
from app.models.lead import Lead
from app.models.note import Note
from app.models.task import Task
from app.services.search_service import SearchService

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


def _service() -> SearchService:
    """Build a search service whose repos are all stubbed out."""
    service = SearchService(FakeSession())
    service._leads = MagicMock()
    service._tasks = MagicMock()
    service._notes = MagicMock()
    return service


def _lead(**overrides: object) -> Lead:
    lead = Lead(organization_id=ORG_ID, email="prospect@example.com")
    lead.id = uuid.uuid4()
    lead.status = LeadStatus.NEW
    for key, value in overrides.items():
        setattr(lead, key, value)
    return lead


def _task(**overrides: object) -> Task:
    task = Task(organization_id=ORG_ID, title="Follow up")
    task.id = uuid.uuid4()
    task.status = TaskStatus.TODO
    task.priority = TaskPriority.MEDIUM
    for key, value in overrides.items():
        setattr(task, key, value)
    return task


def _note(**overrides: object) -> Note:
    note = Note(organization_id=ORG_ID, lead_id=uuid.uuid4(), body="Body text")
    note.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(note, key, value)
    return note


async def test_search_fans_out_to_all_stores() -> None:
    service = _service()
    lead = _lead(first_name="Acme")
    task = _task(title="Call Acme")
    note = _note(body="Acme deal")
    service._leads.search = AsyncMock(return_value=[lead])
    service._tasks.search_tasks = AsyncMock(return_value=[task])
    service._notes.search = AsyncMock(return_value=[note])

    result = await service.search(ORG_ID, query="acme", limit=10)

    service._leads.search.assert_awaited_once_with(
        ORG_ID, query="acme", limit=10
    )
    service._tasks.search_tasks.assert_awaited_once_with(
        ORG_ID, query="acme", limit=10
    )
    service._notes.search.assert_awaited_once_with(
        ORG_ID, query="acme", limit=10
    )
    assert result["query"] == "acme"
    assert result["leads"] == [lead]
    assert result["tasks"] == [task]
    assert result["notes"] == [note]
    assert result["counts"] == {"leads": 1, "tasks": 1, "notes": 1, "total": 3}


async def test_search_returns_empty_sections_when_nothing_matches() -> None:
    service = _service()
    service._leads.search = AsyncMock(return_value=[])
    service._tasks.search_tasks = AsyncMock(return_value=[])
    service._notes.search = AsyncMock(return_value=[])

    result = await service.search(ORG_ID, query="missing", limit=5)

    assert result["leads"] == []
    assert result["tasks"] == []
    assert result["notes"] == []
    assert result["counts"]["total"] == 0
