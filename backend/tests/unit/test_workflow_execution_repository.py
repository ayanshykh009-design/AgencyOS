"""Unit tests: WorkflowExecution guarded transitions clear stale terminal fields."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.workflow_execution import WorkflowExecutionRepository

ORG_ID = uuid.uuid4()
EXECUTION_ID = uuid.uuid4()


class _Scalars:
    def scalar_one_or_none(self):
        return object()


class _Result:
    def scalar_one_or_none(self):
        return _Scalars().scalar_one_or_none()


class RecordingSession(AsyncSession):
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, stmt, params=None):
        self.executed.append(str(stmt))
        return _Result()


def _repo(session: RecordingSession) -> WorkflowExecutionRepository:
    return WorkflowExecutionRepository(session)


def _assert_terminal_fields_cleared(statement: str) -> None:
    for column in ("error", "output", "finished_at", "started_at"):
        assert column in statement


def test_mark_requeued_clears_stale_terminal_fields() -> None:
    session = RecordingSession()

    asyncio.run(_repo(session).mark_requeued(ORG_ID, EXECUTION_ID))

    _assert_terminal_fields_cleared(session.executed[0])


def test_mark_requeued_due_clears_stale_terminal_fields() -> None:
    session = RecordingSession()

    asyncio.run(
        _repo(session).mark_requeued_due(ORG_ID, EXECUTION_ID, due_before=datetime.now(UTC))
    )

    _assert_terminal_fields_cleared(session.executed[0])


def test_mark_started_defensively_clears_stale_terminal_fields() -> None:
    session = RecordingSession()

    asyncio.run(_repo(session).mark_started(ORG_ID, EXECUTION_ID))

    _assert_terminal_fields_cleared(session.executed[0])
