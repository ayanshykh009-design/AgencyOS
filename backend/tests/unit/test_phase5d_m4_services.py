"""Service-layer unit tests for the M4 memory read/write flows.

Covers ``capture_memory`` (skip + dedup rules), ``retrieve_context`` (gated,
bounded retrieval), and ``promote_to_knowledge`` (duplicate-guarded, service
internal) without a database — repositories are mocked.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.models.ai_memory import AiMemory
from app.models.enums import MemoryScope, MemoryType
from app.models.knowledge_item import KnowledgeItem
from app.services.memory_service import MemoryService

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def refresh(self, instance: object) -> None:
        pass


def _make_service(*repo_attrs: str) -> tuple[FakeSession, MemoryService, list]:
    session = FakeSession()
    service = MemoryService(session)
    mocks: list = []
    for attr in repo_attrs:
        m = MagicMock(name=attr)
        setattr(service, attr, m)
        mocks.append(m)
    return session, service, mocks


def _working_memory(content: str = "remember to follow up") -> AiMemory:
    return AiMemory(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        memory_type=MemoryType.WORKING,
        scope=MemoryScope.RESEARCH,
        content=content,
        importance=3,
        metadata_={},
        created_at=datetime.now(UTC),
    )


# -- capture_memory ---------------------------------------------------


async def test_capture_skips_short_content() -> None:
    session, service, mocks = _make_service("_memories")
    memories: MagicMock = mocks[0]
    memories.find_duplicate = AsyncMock()

    result = await service.capture_memory(
        ORG_ID, content="tiny", importance=5, source="research"
    )

    assert result is None
    memories.find_duplicate.assert_not_awaited()
    assert session.added == []


async def test_capture_skips_low_importance() -> None:
    session, service, mocks = _make_service("_memories")
    memories: MagicMock = mocks[0]
    memories.find_duplicate = AsyncMock()

    result = await service.capture_memory(
        ORG_ID, content="a reasonably long observation", importance=1, source="research"
    )

    assert result is None
    memories.find_duplicate.assert_not_awaited()
    assert session.added == []


async def test_capture_dedupes_identical_working_memory() -> None:
    session, service, mocks = _make_service("_memories")
    memories: MagicMock = mocks[0]
    existing = _working_memory()
    memories.find_duplicate = AsyncMock(return_value=existing)

    result = await service.capture_memory(
        ORG_ID, content="  Remember   to follow up  ", importance=3, source="conversation"
    )

    assert result is existing
    memories.find_duplicate.assert_awaited_once()
    assert session.committed is False
    assert session.added == []


async def test_capture_stores_new_working_memory_with_inferred_scope() -> None:
    session, service, mocks = _make_service("_memories")
    memories: MagicMock = mocks[0]
    memories.find_duplicate = AsyncMock(return_value=None)
    memories.add = MagicMock(side_effect=session.add)

    result = await service.capture_memory(
        ORG_ID, content="Lead is interested in a product demo", importance=4, source="workflow"
    )

    assert result is not None
    assert result.scope is MemoryScope.WORKFLOW
    assert session.committed is True
    assert session.added[0] is result
    memories.find_duplicate.assert_awaited_once()


async def test_capture_never_dedupes_long_term() -> None:
    session, service, mocks = _make_service("_memories")
    memories: MagicMock = mocks[0]
    memories.find_duplicate = AsyncMock()

    result = await service.capture_memory(
        ORG_ID,
        content="Company prefers quarterly calls",
        importance=4,
        memory_type=MemoryType.LONG_TERM,
        scope=MemoryScope.MANUAL,
        metadata_={"category": "business"},
    )

    assert result is not None
    assert result.memory_type is MemoryType.LONG_TERM
    memories.find_duplicate.assert_not_awaited()


# -- retrieve_context -------------------------------------------------


async def test_retrieve_context_returns_ranked_bounded_block(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MEMORY_RETRIEVAL_LIMIT", 3)
    monkeypatch.setattr(settings, "MEMORY_CONTEXT_MAX_CHARS", 2500)
    session, service, mocks = _make_service("_memories")
    memories: MagicMock = mocks[0]
    candidates = [
        _working_memory("context candidate A"),
        _working_memory("context candidate B"),
    ]
    memories.list_ranked = AsyncMock(return_value=candidates)

    block = await service.retrieve_context(ORG_ID, scope=MemoryScope.RESEARCH)

    assert "context candidate A" in block
    assert "context candidate B" in block
    memories.list_ranked.assert_awaited_once_with(ORG_ID, scope=MemoryScope.RESEARCH, limit=12)


async def test_retrieve_context_empty_when_no_candidates(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MEMORY_RETRIEVAL_LIMIT", 10)
    session, service, mocks = _make_service("_memories")
    memories: MagicMock = mocks[0]
    memories.list_ranked = AsyncMock(return_value=[])

    assert await service.retrieve_context(ORG_ID) == ""


# -- promote_to_knowledge ----------------------------------------------


async def test_promote_rejects_blank_category() -> None:
    session, service, _ = _make_service("_memories", "_knowledge")

    with pytest.raises(AppError) as exc:
        await service.promote_to_knowledge(ORG_ID, uuid.uuid4(), category="   ")

    assert exc.value.status_code == 400
    assert session.committed is False


async def test_promote_returns_existing_knowledge_idempotently() -> None:
    session, service, mocks = _make_service("_memories", "_knowledge")
    memories, knowledge = mocks
    memory = _working_memory()
    memories.get_or_404 = AsyncMock(return_value=memory)
    existing = KnowledgeItem(
        organization_id=ORG_ID,
        source_memory_id=memory.id,
        title="t",
        content="c",
        category="business",
    )
    knowledge.get_by_source_memory = AsyncMock(return_value=existing)
    knowledge.add = MagicMock(side_effect=session.add)

    result = await service.promote_to_knowledge(ORG_ID, memory.id, category="business")

    assert result is existing
    knowledge.get_by_source_memory.assert_awaited_once_with(ORG_ID, memory.id)
    assert session.added == []
    assert session.committed is False


async def test_promote_creates_knowledge_with_provenance() -> None:
    session, service, mocks = _make_service("_memories", "_knowledge")
    memories, knowledge = mocks
    memory = _working_memory("durable insight worth promoting")
    memories.get_or_404 = AsyncMock(return_value=memory)
    knowledge.get_by_source_memory = AsyncMock(return_value=None)
    knowledge.add = MagicMock(side_effect=session.add)

    result = await service.promote_to_knowledge(
        ORG_ID, memory.id, category="knowledge", tags=["insight"]
    )

    assert session.committed is True
    assert session.added[0] is result
    assert result.source_memory_id == memory.id
    assert result.content == memory.content
    assert result.metadata_["origin"] == "memory"
    assert result.metadata_["source_memory_id"] == str(memory.id)


async def test_promote_forwards_not_found() -> None:
    session, service, mocks = _make_service("_memories", "_knowledge")
    memories, knowledge = mocks
    memories.get_or_404 = AsyncMock(
        side_effect=AppError("ai_memory.not_found", "AiMemory not found", 404)
    )
    knowledge.get_by_source_memory = AsyncMock()

    with pytest.raises(AppError) as exc:
        await service.promote_to_knowledge(ORG_ID, uuid.uuid4(), category="business")

    assert exc.value.status_code == 404
    knowledge.get_by_source_memory.assert_not_awaited()
