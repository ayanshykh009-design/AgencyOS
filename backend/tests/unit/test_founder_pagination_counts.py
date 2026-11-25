"""Pagination totals must be counted with the same filters as the page query."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import FounderProposalStatus
from app.repositories.founder_action_proposal import FounderActionProposalRepository
from app.repositories.founder_chat import FounderChatRepository

ORG = uuid.uuid4()


def _session_with_count(value: int) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one.return_value = value
    session.execute = AsyncMock(return_value=result)
    return session


async def test_proposal_count_uses_org_and_status_filters() -> None:
    session = _session_with_count(12)
    repo = FounderActionProposalRepository(session)

    assert await repo.count_by_status(ORG, status=FounderProposalStatus.PROPOSED) == 12
    stmt = session.execute.await_args.args[0]
    assert len(stmt._where_criteria) == 2  # organization_id + status

    session = _session_with_count(30)
    assert await FounderActionProposalRepository(session).count_by_status(ORG) == 30
    assert len(session.execute.await_args.args[0]._where_criteria) == 1


async def test_conversation_count_matches_list_archive_filter() -> None:
    session = _session_with_count(7)
    repo = FounderChatRepository(session)

    assert await repo.count_conversations(ORG) == 7
    assert len(session.execute.await_args.args[0]._where_criteria) == 2  # org + not archived

    session = _session_with_count(9)
    assert await FounderChatRepository(session).count_conversations(ORG, include_archived=True) == 9
    assert len(session.execute.await_args.args[0]._where_criteria) == 1
