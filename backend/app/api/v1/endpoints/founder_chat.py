"""Founder Assistant API — chat, conversations, and approval-gated proposals."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.permissions import Permission, require_permission
from app.models.enums import FounderProposalStatus
from app.schemas.founder_assistant import (
    FounderChatRequest,
    FounderChatResponse,
    FounderConversationList,
    FounderConversationRead,
    FounderProposalDecision,
    FounderProposalList,
    FounderProposalRead,
)
from app.services.founder_action_service import FounderActionService
from app.services.founder_chat_service import FounderChatService

router = APIRouter()

_read = Depends(require_permission(Permission.FOUNDER_READ))
_manage = Depends(require_permission(Permission.FOUNDER_MANAGE))


@router.post(
    "/chat",
    response_model=FounderChatResponse,
    summary="Send a message to the Founder AI Assistant",
    dependencies=[_manage],
)
async def founder_chat(
    body: FounderChatRequest, db: DbSession, current_user: CurrentUser
) -> FounderChatResponse:
    service = FounderChatService(db)
    result = await service.send_message(
        current_user.organization_id,
        current_user,
        conversation_id=body.conversation_id,
        message=body.message,
    )
    proposals = [FounderProposalRead.model_validate(p) for p in result["proposals"]]
    return FounderChatResponse(
        conversation_id=uuid.UUID(result["conversation_id"]),
        message=result["message"],
        proposals=proposals,
        intent=result["intent"],
        ok=result["ok"],
        error=result["error"],
    )


@router.get(
    "/conversations",
    response_model=FounderConversationList,
    summary="List founder conversations",
    dependencies=[_read],
)
async def list_conversations(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_archived: bool = False,
) -> FounderConversationList:
    service = FounderChatService(db)
    items = await service.list_conversations(
        current_user.organization_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    return FounderConversationList(
        items=[FounderConversationRead.model_validate(c) for c in items], total=len(items)
    )


@router.get(
    "/conversations/{conversation_id}",
    summary="Get a founder conversation with its messages",
    dependencies=[_read],
)
async def get_conversation(
    conversation_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> dict:
    service = FounderChatService(db)
    return await service.get_conversation(current_user.organization_id, conversation_id)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a founder conversation",
    dependencies=[_manage],
)
async def delete_conversation(
    conversation_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> None:
    service = FounderChatService(db)
    deleted = await service.delete_conversation(current_user.organization_id, conversation_id)
    if not deleted:
        raise AppError(
            code="founder_conversation.not_found",
            message="Conversation not found",
            status_code=404,
        )


@router.get(
    "/proposals",
    response_model=FounderProposalList,
    summary="List founder action proposals",
    dependencies=[_read],
)
async def list_proposals(
    db: DbSession,
    current_user: CurrentUser,
    proposal_status: FounderProposalStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FounderProposalList:
    service = FounderActionService(db)
    items = await service.list_proposals(
        current_user.organization_id,
        status=proposal_status,
        limit=limit,
        offset=offset,
    )
    return FounderProposalList(
        items=[FounderProposalRead.model_validate(p) for p in items], total=len(items)
    )


@router.post(
    "/proposals/{proposal_id}/decide",
    response_model=FounderProposalRead,
    summary="Approve or deny a founder action proposal",
    dependencies=[_manage],
)
async def decide_proposal(
    proposal_id: uuid.UUID,
    body: FounderProposalDecision,
    db: DbSession,
    current_user: CurrentUser,
) -> FounderProposalRead:
    service = FounderActionService(db)
    proposal = await service.decide_proposal(
        current_user.organization_id,
        current_user.id,
        proposal_id,
        approve=body.approve,
        decision_note=body.decision_note,
    )
    return FounderProposalRead.model_validate(proposal)
