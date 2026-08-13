"""Conversation endpoints: threads and thread messages."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.conversation import (
    ConversationCreate,
    ConversationMessageCreate,
    ConversationMessageRead,
    ConversationRead,
    ConversationUpdate,
)
from app.services.conversation_service import ConversationService

router = APIRouter()


@router.get(
    "/open",
    response_model=list[ConversationRead],
    summary="List open conversations",
)
async def list_open(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ConversationRead]:
    service = ConversationService(db)
    conversations = await service.list_open(
        current_user.organization_id, limit=limit, offset=offset
    )
    return [ConversationRead.model_validate(c) for c in conversations]


@router.get(
    "/leads/{lead_id}",
    response_model=list[ConversationRead],
    summary="List conversations for a lead",
)
async def list_for_lead(
    lead_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> list[ConversationRead]:
    service = ConversationService(db)
    conversations = await service.list_for_lead(current_user.organization_id, lead_id)
    return [ConversationRead.model_validate(c) for c in conversations]


@router.post(
    "",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a conversation",
)
async def create_conversation(
    body: ConversationCreate, db: DbSession, current_user: CurrentUser
) -> ConversationRead:
    service = ConversationService(db)
    data = body.model_dump()
    data["organization_id"] = current_user.organization_id
    conversation = await service.create(current_user.organization_id, data)
    return ConversationRead.model_validate(conversation)


@router.get(
    "/{conversation_id}",
    response_model=ConversationRead,
    summary="Get a conversation",
)
async def get_conversation(
    conversation_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ConversationRead:
    service = ConversationService(db)
    conversation = await service.get(current_user.organization_id, conversation_id)
    return ConversationRead.model_validate(conversation)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationRead,
    summary="Update a conversation",
)
async def update_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> ConversationRead:
    service = ConversationService(db)
    conversation = await service.update(
        current_user.organization_id,
        conversation_id,
        body.model_dump(exclude_unset=True),
    )
    return ConversationRead.model_validate(conversation)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[ConversationMessageRead],
    summary="List messages in a conversation",
)
async def list_messages(
    conversation_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[ConversationMessageRead]:
    service = ConversationService(db)
    messages = await service.list_messages(
        current_user.organization_id, conversation_id, limit=limit, offset=offset
    )
    return [ConversationMessageRead.model_validate(m) for m in messages]


@router.post(
    "/{conversation_id}/messages",
    response_model=ConversationMessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a message to a conversation",
)
async def add_message(
    conversation_id: uuid.UUID,
    body: ConversationMessageCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ConversationMessageRead:
    service = ConversationService(db)
    data = body.model_dump()
    data["organization_id"] = current_user.organization_id
    message = await service.add_message(current_user.organization_id, conversation_id, data)
    return ConversationMessageRead.model_validate(message)
