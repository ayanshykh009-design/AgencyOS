"""Memory service: AI memory + durable knowledge items.

M2/M3 thin orchestration over the repositories (CRUD), extended in M4 with
the AI memory read/write flows:

- ``retrieve_context`` — deterministic retrieval pipeline (org-scoped candidate
  fetch → pure ranking → bounded context block) feeding the AI system prompt.
- ``capture_memory`` — the AI write path: applies the skip rules (content
  length / importance floor) and write-time dedup for working memories.
- ``promote_to_knowledge`` — service-internal promotion of a working memory to
  a durable knowledge item (duplicate-guarded by ``source_memory_id``; no API
  route exposes this).

The manual CRUD entry points are unchanged and never auto-skip or dedup.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.memory.assembler import assemble_memory_context
from app.memory.classification import infer_scope, normalize_content
from app.memory.scoring import rank_memories
from app.models.ai_memory import AiMemory
from app.models.enums import MemoryScope, MemoryType
from app.models.knowledge_item import KnowledgeItem
from app.repositories.ai_memory import AiMemoryRepository
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.services.base import commit_with_retry

_DEDUP_WINDOW = timedelta(hours=24)
_MIN_CONTENT_CHARS = 10
_MIN_IMPORTANCE = 2
_MAX_RETRIEVAL_CANDIDATES = 100


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

    # -- M4: AI memory read/write flows ------------------------------------

    async def capture_memory(
        self,
        organization_id: uuid.UUID,
        *,
        memory_type: MemoryType = MemoryType.WORKING,
        scope: MemoryScope | None = None,
        source_id: uuid.UUID | None = None,
        source: str | None = None,
        title: str | None = None,
        content: str,
        importance: int,
        tags: list[str] | None = None,
        metadata_: dict[str, Any] | None = None,
        ttl_window: timedelta | None = None,
    ) -> AiMemory | None:
        """Write path for AI-captured memories (dedup + skip rules).

        Returns ``None`` when the write is skipped (content too short or below
        the importance floor). For working memories, an identical entry
        created within ``ttl_window`` (default 24h) returns the existing row
        without writing. Manual API creates never pass through this method.
        """
        clean_content = (content or "").strip()
        if len(clean_content) < _MIN_CONTENT_CHARS or int(importance or 0) < _MIN_IMPORTANCE:
            return None
        resolved_scope = scope or infer_scope(source)
        window = ttl_window or _DEDUP_WINDOW
        if memory_type == MemoryType.WORKING:
            existing = await self._memories.find_duplicate(
                organization_id,
                normalize_content(clean_content),
                window,
            )
            if existing is not None:
                return existing
        memory = AiMemory(
            organization_id=organization_id,
            memory_type=memory_type,
            scope=resolved_scope,
            source_id=source_id,
            title=title,
            content=clean_content,
            importance=int(importance),
            tags=list(tags or []),
            metadata_=dict(metadata_ or {}),
        )
        self._memories.add(memory)
        await commit_with_retry(self._session)
        return memory

    async def retrieve_context(
        self,
        organization_id: uuid.UUID,
        *,
        scope: MemoryScope | None = None,
        limit: int | None = None,
        max_chars: int | None = None,
        metadata_: dict[str, Any] | None = None,
    ) -> str:
        """Retrieve ranked memory context for the AI system prompt.

        Org-scoped candidate fetch (bounded), pure ranking, then assembly into
        a bounded plain-text block. Returns ``""`` when nothing qualifies.
        Callers gate this on ``settings.AI_MEMORY_ENABLED``.
        """
        retrieval_limit = max(1, min(limit or settings.MEMORY_RETRIEVAL_LIMIT, 100))
        budget = max(500, max_chars or settings.MEMORY_CONTEXT_MAX_CHARS)
        candidate_limit = min(max(retrieval_limit * 4, 1), _MAX_RETRIEVAL_CANDIDATES)
        candidates = await self._memories.list_ranked(
            organization_id,
            scope=scope,
            limit=candidate_limit,
        )
        ranked = rank_memories(candidates, metadata_)
        return assemble_memory_context(ranked, max_items=retrieval_limit, max_chars=budget)

    async def promote_to_knowledge(
        self,
        organization_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        category: str,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeItem:
        """Promote a working memory into a durable knowledge item.

        Service-internal only (no API route). Duplicate-guarded: a knowledge
        item already linked to ``memory_id`` (by ``source_memory_id``) is
        returned unchanged instead of duplicating. ``category`` must be a
        non-blank string; provenance is recorded in the item's metadata.
        """
        category = (category or "").strip()
        if not category:
            raise AppError(
                code="knowledge.category_required",
                message="Knowledge category is required",
                status_code=400,
            )
        memory = await self._memories.get_or_404(organization_id, memory_id)
        existing = await self._knowledge.get_by_source_memory(organization_id, memory_id)
        if existing is not None:
            return existing
        item = KnowledgeItem(
            organization_id=organization_id,
            source_memory_id=memory.id,
            title=(title or memory.title or "").strip() or "Knowledge",
            content=memory.content,
            category=category,
            tags=list(tags or []),
            metadata_={
                **(memory.metadata_ or {}),
                "origin": "memory",
                "source_memory_id": str(memory.id),
            },
        )
        self._knowledge.add(item)
        await commit_with_retry(self._session)
        return item

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
