"""Memory endpoints: AI memory + durable knowledge items."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.models.enums import MemoryScope, MemoryType
from app.schemas.ai_memory import AiMemoryCreate, AiMemoryListResponse, AiMemoryRead, AiMemoryUpdate
from app.schemas.knowledge_item import (
    KnowledgeItemCreate,
    KnowledgeItemListResponse,
    KnowledgeItemRead,
    KnowledgeItemUpdate,
)
from app.services.memory_service import MemoryService

router = APIRouter()

_read = Depends(require_permission(Permission.MEMORY_READ))
_write = Depends(require_permission(Permission.MEMORY_WRITE))


def _metadata_from_dump(data: dict) -> dict:
    # The python field name is ``metadata``; model_dump() emits that key, so pop
    # it here and hand the raw value to the service as ``metadata_``.
    meta = data.pop("metadata", None)
    return meta or {}


@router.get(
    "",
    response_model=AiMemoryListResponse,
    summary="List AI memories (optional type/scope filter)",
    dependencies=[_read],
)
async def list_memories(
    db: DbSession,
    current_user: CurrentUser,
    memory_type: MemoryType | None = None,
    scope: MemoryScope | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AiMemoryListResponse:
    service = MemoryService(db)
    items = await service.list_memories(
        current_user.organization_id,
        memory_type=memory_type,
        scope=scope,
        limit=limit,
        offset=offset,
    )
    return AiMemoryListResponse(
        items=[AiMemoryRead.model_validate(m) for m in items], total=len(items)
    )


@router.post(
    "",
    response_model=AiMemoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an AI memory",
    dependencies=[_write],
)
async def create_memory(
    body: AiMemoryCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> AiMemoryRead:
    service = MemoryService(db)
    data = body.model_dump(exclude={"organization_id"})
    metadata = _metadata_from_dump(data)
    memory = await service.create_memory(current_user.organization_id, metadata_=metadata, **data)
    return AiMemoryRead.model_validate(memory)


@router.get(
    "/knowledge",
    response_model=KnowledgeItemListResponse,
    summary="List knowledge items (optional category filter)",
    dependencies=[_read],
)
async def list_knowledge(
    db: DbSession,
    current_user: CurrentUser,
    category: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> KnowledgeItemListResponse:
    service = MemoryService(db)
    items = await service.list_knowledge(
        current_user.organization_id, category=category, limit=limit, offset=offset
    )
    return KnowledgeItemListResponse(
        items=[KnowledgeItemRead.model_validate(k) for k in items], total=len(items)
    )


@router.get(
    "/knowledge/search",
    response_model=KnowledgeItemListResponse,
    summary="Substring search over knowledge title/content",
    dependencies=[_read],
)
async def search_knowledge(
    db: DbSession,
    current_user: CurrentUser,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> KnowledgeItemListResponse:
    service = MemoryService(db)
    items = await service.search_knowledge(current_user.organization_id, query=q, limit=limit)
    return KnowledgeItemListResponse(
        items=[KnowledgeItemRead.model_validate(k) for k in items], total=len(items)
    )


@router.post(
    "/knowledge",
    response_model=KnowledgeItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a knowledge item",
    dependencies=[_write],
)
async def create_knowledge(
    body: KnowledgeItemCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> KnowledgeItemRead:
    service = MemoryService(db)
    data = body.model_dump(exclude={"organization_id"})
    metadata = _metadata_from_dump(data)
    item = await service.create_knowledge(current_user.organization_id, metadata_=metadata, **data)
    return KnowledgeItemRead.model_validate(item)


@router.get(
    "/knowledge/{item_id}",
    response_model=KnowledgeItemRead,
    summary="Get a knowledge item",
    dependencies=[_read],
)
async def get_knowledge(
    item_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> KnowledgeItemRead:
    service = MemoryService(db)
    item = await service.get_knowledge(current_user.organization_id, item_id)
    return KnowledgeItemRead.model_validate(item)


@router.patch(
    "/knowledge/{item_id}",
    response_model=KnowledgeItemRead,
    summary="Update a knowledge item",
    dependencies=[_write],
)
async def update_knowledge(
    item_id: uuid.UUID,
    body: KnowledgeItemUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> KnowledgeItemRead:
    service = MemoryService(db)
    data = body.model_dump(exclude_unset=True)
    metadata = data.pop("metadata_", None)
    kwargs = {**({"metadata_": metadata} if metadata is not None else {})}
    item = await service.update_knowledge(current_user.organization_id, item_id, **data, **kwargs)
    return KnowledgeItemRead.model_validate(item)


@router.delete(
    "/knowledge/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge item",
    dependencies=[_write],
)
async def delete_knowledge(item_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    service = MemoryService(db)
    await service.delete_knowledge(current_user.organization_id, item_id)


@router.get(
    "/{memory_id}",
    response_model=AiMemoryRead,
    summary="Get an AI memory",
    dependencies=[_read],
)
async def get_memory(
    memory_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> AiMemoryRead:
    service = MemoryService(db)
    memory = await service.get_memory(current_user.organization_id, memory_id)
    return AiMemoryRead.model_validate(memory)


@router.patch(
    "/{memory_id}",
    response_model=AiMemoryRead,
    summary="Update an AI memory",
    dependencies=[_write],
)
async def update_memory(
    memory_id: uuid.UUID,
    body: AiMemoryUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> AiMemoryRead:
    service = MemoryService(db)
    data = body.model_dump(exclude_unset=True)
    metadata = data.pop("metadata_", None)
    kwargs = {**({"metadata_": metadata} if metadata is not None else {})}
    memory = await service.update_memory(current_user.organization_id, memory_id, **data, **kwargs)
    return AiMemoryRead.model_validate(memory)


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an AI memory",
    dependencies=[_write],
)
async def delete_memory(memory_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    service = MemoryService(db)
    await service.delete_memory(current_user.organization_id, memory_id)
