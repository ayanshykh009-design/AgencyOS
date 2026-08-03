"""Service-layer unit tests: task CRUD, completion, recurrence, reminders."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.enums import (
    ActivityEventType,
    RecurrenceFrequency,
    TaskPriority,
    TaskStatus,
    UserRole,
)
from app.models.lead import Lead
from app.models.task import Task
from app.models.user import User
from app.services.task_service import TaskService

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


def _make_task(**overrides: object) -> Task:
    task = Task(
        organization_id=ORG_ID,
        title="Follow up",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
    )
    task.id = uuid.uuid4()
    for key, value in overrides.items():
        setattr(task, key, value)
    return task


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
    user.is_active = True
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _service(session: FakeSession, **repos: object) -> TaskService:
    service = TaskService(session)
    service._tasks = MagicMock()
    service._leads = MagicMock()
    service._users = MagicMock()
    service._activity = MagicMock()
    for name, fake in repos.items():
        setattr(service, name, fake)
    return service


def _wire_add(service: TaskService, session: FakeSession) -> None:
    service._tasks.add = MagicMock(side_effect=session.add)
    service._activity.add = MagicMock(side_effect=session.add)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_persists_and_emits_event() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    due = datetime.now(UTC) + timedelta(days=1)

    task = await service.create(
        ORG_ID,
        _make_user(),
        title="  Send proposal  ",
        due_at=due,
        priority=TaskPriority.HIGH,
    )

    assert task.title == "Send proposal"
    assert task.status is TaskStatus.TODO
    assert task.priority is TaskPriority.HIGH
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.TASK_CREATED
    assert entry.entity_type == "task"
    assert session.committed is True


@pytest.mark.asyncio
async def test_create_rejects_blank_title() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)

    with pytest.raises(AppError) as exc_info:
        await service.create(ORG_ID, _make_user(), title="   ")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "task.title_required"


@pytest.mark.asyncio
async def test_create_validates_lead_exists() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    service._leads.get_or_404 = AsyncMock(
        side_effect=AppError("lead.not_found", "Lead not found", 404)
    )

    with pytest.raises(AppError) as exc_info:
        await service.create(
            ORG_ID, _make_user(), title="Task", lead_id=uuid.uuid4()
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "lead.not_found"


@pytest.mark.asyncio
async def test_create_rejects_inactive_assignee() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    service._users.get_or_404 = AsyncMock(return_value=_make_user(is_active=False))

    with pytest.raises(AppError) as exc_info:
        await service.create(
            ORG_ID, _make_user(), title="Task", assignee_user_id=uuid.uuid4()
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "task.invalid_assignee"


@pytest.mark.asyncio
async def test_create_rejects_reminder_after_due() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    due = datetime.now(UTC) + timedelta(days=1)
    reminder = due + timedelta(hours=1)

    with pytest.raises(AppError) as exc_info:
        await service.create(
            ORG_ID,
            _make_user(),
            title="Task",
            due_at=due,
            reminder_at=reminder,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "task.reminder_after_due"


@pytest.mark.asyncio
async def test_create_defaults_recurrence_interval() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)

    task = await service.create(
        ORG_ID,
        _make_user(),
        title="Standup",
        recurrence_frequency=RecurrenceFrequency.DAILY,
    )

    assert task.recurrence_interval == 1


@pytest.mark.asyncio
async def test_create_rejects_interval_without_frequency() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)

    with pytest.raises(AppError) as exc_info:
        await service.create(ORG_ID, _make_user(), title="Task", recurrence_interval=2)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "task.recurrence_requires_frequency"


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_changes_fields_and_emits_event() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    task = _make_task()
    service._tasks.get_or_404 = AsyncMock(return_value=task)

    result = await service.update(
        ORG_ID,
        _make_user(),
        task.id,
        title="Renamed",
        priority=TaskPriority.URGENT,
    )

    assert result.title == "Renamed"
    assert result.priority is TaskPriority.URGENT
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.TASK_UPDATED
    assert session.committed is True


@pytest.mark.asyncio
async def test_update_reopens_completed_task() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    task = _make_task(
        status=TaskStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    service._tasks.get_or_404 = AsyncMock(return_value=task)

    await service.update(
        ORG_ID, _make_user(), task.id, status=TaskStatus.IN_PROGRESS
    )

    assert task.status is TaskStatus.IN_PROGRESS
    assert task.completed_at is None


# ---------------------------------------------------------------------------
# complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_marks_task_done() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    task = _make_task()
    service._tasks.get_or_404 = AsyncMock(return_value=task)

    result = await service.complete(ORG_ID, _make_user(), task.id)

    assert result.status is TaskStatus.COMPLETED
    assert result.completed_at is not None
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.TASK_COMPLETED
    assert entry.metadata_ == {"recurred": False}
    assert session.committed is True


@pytest.mark.asyncio
async def test_complete_is_idempotent() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    task = _make_task(status=TaskStatus.COMPLETED, completed_at=datetime.now(UTC))
    service._tasks.get_or_404 = AsyncMock(return_value=task)

    await service.complete(ORG_ID, _make_user(), task.id)

    assert not any(isinstance(o, ActivityLog) for o in session.added)


@pytest.mark.asyncio
async def test_complete_recurring_advances_schedule() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    due = datetime(2026, 3, 2, 9, tzinfo=UTC)
    task = _make_task(
        due_at=due,
        reminder_at=due - timedelta(hours=1),
        recurrence_frequency=RecurrenceFrequency.WEEKLY,
        recurrence_interval=2,
    )
    service._tasks.get_or_404 = AsyncMock(return_value=task)

    result = await service.complete(ORG_ID, _make_user(), task.id)

    assert result.status is TaskStatus.TODO
    assert result.completed_at is None
    assert result.due_at == due + timedelta(weeks=2)
    assert result.reminder_at == due + timedelta(weeks=2) - timedelta(hours=1)
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.TASK_COMPLETED
    assert entry.metadata_ == {"recurred": True}


@pytest.mark.asyncio
async def test_complete_recurring_monthly_clamps_day() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    task = _make_task(
        due_at=datetime(2026, 1, 31, 12, tzinfo=UTC),
        recurrence_frequency=RecurrenceFrequency.MONTHLY,
        recurrence_interval=1,
    )
    service._tasks.get_or_404 = AsyncMock(return_value=task)

    result = await service.complete(ORG_ID, _make_user(), task.id)

    assert result.due_at == datetime(2026, 2, 28, 12, tzinfo=UTC)
    assert result.status is TaskStatus.TODO


@pytest.mark.asyncio
async def test_update_with_status_completed_closes_task() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    task = _make_task()
    service._tasks.get_or_404 = AsyncMock(return_value=task)

    result = await service.update(
        ORG_ID, _make_user(), task.id, status=TaskStatus.COMPLETED
    )

    assert result.status is TaskStatus.COMPLETED
    assert result.completed_at is not None
    entries = [o for o in session.added if isinstance(o, ActivityLog)]
    assert all(e.event_type is ActivityEventType.TASK_COMPLETED for e in entries)


# ---------------------------------------------------------------------------
# delete / reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_task_and_emits_event() -> None:
    session = FakeSession()
    service = _service(session)
    _wire_add(service, session)
    task = _make_task()
    service._tasks.get_or_404 = AsyncMock(return_value=task)
    service._tasks.delete = AsyncMock()

    await service.delete(ORG_ID, _make_user(), task.id)

    service._tasks.delete.assert_awaited_once_with(task)
    entry = next(o for o in session.added if isinstance(o, ActivityLog))
    assert entry.event_type is ActivityEventType.TASK_DELETED
    assert session.committed is True


@pytest.mark.asyncio
async def test_get_unknown_task_raises_404() -> None:
    session = FakeSession()
    service = _service(session)
    service._tasks.get_or_404 = AsyncMock(
        side_effect=AppError("task.not_found", "Task not found", 404)
    )

    with pytest.raises(AppError) as exc_info:
        await service.get(ORG_ID, uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "task.not_found"


@pytest.mark.asyncio
async def test_due_reminders_delegates_to_repository() -> None:
    session = FakeSession()
    service = _service(session)
    task = _make_task(reminder_at=datetime.now(UTC) - timedelta(minutes=5))
    service._tasks.list_due_for_reminder = AsyncMock(return_value=[task])

    result = await service.due_reminders(ORG_ID)

    assert result == [task]
    service._tasks.list_due_for_reminder.assert_awaited_once()
