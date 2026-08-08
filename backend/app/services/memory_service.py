"""Memory service: AI memory + durable knowledge items.

Thin orchestration over the M2 repositories. Memory *retrieval* and write
flows with AI reasoning land in M4; this service is pure CRUD.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.ai_memory import AiMemory
from app.models.enums import MemoryScope, MemoryType
from app.models.knowledge_item import KnowledgeItem
from app.repositories.ai_memory import AiMemoryRepository
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.services.base import commit_with_retry


class MemoryService:
    """Owns memory/knowledge rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._memories = AiMemoryRepository(session)
        self._knowledge = KnowledgeItemRepository(session)

    # -- memories ------------------------------------------------------

    async def list_memories(
        self,
        organization_id: uuid.UUID,
        *,
        memory_type: MemoryType | None = None,
        scope: MemoryScope | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AiMemory]:
        return await self._memories.list_by_scope(
            organization_id,
            memory_type=memory_type,
            scope=scope,
            limit=limit,
            offset=offset,
        )

    async def get_memory(self, organization_id: uuid.UUID, memory_id: uuid.UUID) -> AiMemory:
        return await self._memories.get_or_404(organization_id, memory_id)

    async def create_memory(
        self,
        organization_id: uuid.UUID,
        *,
        memory_type: MemoryType,
        scope: MemoryScope,
        source_id: uuid.UUID | None,
        title: str | None,
        content: str,
        importance: int,
        tags: list[str],
        metadata_: dict[str, Any],
    ) -> AiMemory:
        memory = AiMemory(
            organization_id=organization_id,
            memory_type=memory_type,
            scope=scope,
            source_id=source_id,
            title=title,
            content=content,
            importance=importance,
            tags=tags,
            metadata_=metadata_,
        )
        self._memories.add(memory)
        await commit_with_retry(self._session)
        return memory

    async def update_memory(
        self,
        organization_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        scope: MemoryScope | None = None,
        source_id: uuid.UUID | None = None,
        title: str | None = None,
        content: str | None = None,
        importance: int | None = None,
        tags: list[str] | None = None,
        metadata_: dict[str, Any] | None = None,
    ) -> AiMemory:
        memory = await self._memories.get_or_404(organization_id, memory_id)
        if scope is not None:
            memory.scope = scope
        if source_id is not None:
            memory.source_id = source_id
        if title is not None:
            memory.title = title
        if content is not None:
            memory.content = content
        if importance is not None:
            memory.importance = importance
        if tags is not None:
            memory.tags = tags
        if metadata_ is not None:
            memory.metadata_ = metadata_
        await commit_with_retry(self._session)
        return memory

    async def delete_memory(self, organization_id: uuid.UUID, memory_id: uuid.UUID) -> None:
        if not await self._memories.delete(organization_id, memory_id):
            raise AppError(
                code="ai_memory.not_found",
                message="AiMemory not found",
                status_code=404,
            )
        await commit_with_retry(self._session)

    # -- knowledge -------------------------------------------------------

    async def list_knowledge(
        self,
        organization_id: uuid.UUID,
        *,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeItem]:
        return await self._knowledge.list_by_category(
            organization_id, category=category, limit=limit, offset=offset
        )

    async def search_knowledge(
        self, organization_id: uuid.UUID, *, query: str, limit: int = 50
    ) -> list[KnowledgeItem]:
        if not query.strip():
            raise AppError(
                code="knowledge.search_required",
                message="Search query is required",
                status_code=400,
            )
        return await self._knowledge.search(organization_id, query=query.strip(), limit=limit)

    async def get_knowledge(
        self, organization_id: uuid.UUID, item_id: uuid.UUID
    ) -> KnowledgeItem:
        return await self._knowledge.get_or_404(organization_id, item_id)

    async def create_knowledge(
        self,
        organization_id: uuid.UUID,
        *,
        source_memory_id: uuid.UUID | None,
        title: str,
        content: str,
        category: str,
        tags: list[str],
        metadata_: dict[str, Any],
    ) -> KnowledgeItem:
        item = KnowledgeItem(
            organization_id=organization_id,
            source_memory_id=source_memory_id,
            title=title,
            content=content,
            category=category,
            tags=tags,
            metadata_=metadata_,
        )
        self._knowledge.add(item)
        await commit_with_retry(self._session)
        return item

    async def update_knowledge(
        self,
        organization_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        source_memory_id: uuid.UUID | None = None,
        title: str | None = None,
        content: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        metadata_: dict[str, Any] | None = None,
    ) -> KnowledgeItem:
        item = await self._knowledge.get_or_404(organization_id, item_id)
        if source_memory_id is not None:
            item.source_memory_id = source_memory_id
        if title is not None:
            item.title = title
        if content is not None:
            item.content = content
        if category is not None:
            item.category = category
        if tags is not None:
            item.tags = tags
        if metadata_ is not None:
            item.metadata_ = metadata_
        await commit_with_retry(self._session)
        return item

    async def delete_knowledge(
        self, organization_id: uuid.UUID, item_id: uuid.UUID
    ) -> None:
        if not await self._knowledge.delete(organization_id, item_id):
            raise AppError(
                code="knowledge_item.not_found",
                message="KnowledgeItem not found",
                status_code=404,
            )
        await commit_with_retry(self._session)
