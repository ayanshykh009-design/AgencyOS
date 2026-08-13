"""Outreach endpoints: message templates, attempts, follow-ups, manual queue."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, require_role
from app.models.enums import OutreachChannel, OutreachStatus, UserRole
from app.schemas.outreach import (
    FollowUpCreate,
    FollowUpRead,
    FollowUpUpdate,
    ManualOutreachQueueCreate,
    ManualOutreachQueueRead,
    ManualOutreachQueueUpdate,
    OutreachAttemptCreate,
    OutreachAttemptRead,
    OutreachAttemptUpdate,
    OutreachMessageCreate,
    OutreachMessageRead,
    OutreachMessageUpdate,
)
from app.services.outreach_service import OutreachService

router = APIRouter()

_admin_only = require_role(UserRole.OWNER, UserRole.ADMIN)


# -- message templates ---------------------------------------------------


@router.get(
    "/messages",
    response_model=list[OutreachMessageRead],
    summary="List message templates",
)
async def list_messages(
    db: DbSession,
    current_user: CurrentUser,
    channel: OutreachChannel | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[OutreachMessageRead]:
    service = OutreachService(db)
    messages = await service.list_messages(
        current_user.organization_id, channel=channel, limit=limit, offset=offset
    )
    return [OutreachMessageRead.model_validate(m) for m in messages]


@router.post(
    "/messages",
    response_model=OutreachMessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a message template",
    dependencies=[Depends(_admin_only)],
)
async def create_message(
    body: OutreachMessageCreate, db: DbSession, current_user: CurrentUser
) -> OutreachMessageRead:
    service = OutreachService(db)
    message = await service.create_message(current_user.organization_id, body.model_dump())
    return OutreachMessageRead.model_validate(message)


@router.get(
    "/messages/{message_id}",
    response_model=OutreachMessageRead,
    summary="Get a message template",
)
async def get_message(
    message_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> OutreachMessageRead:
    service = OutreachService(db)
    message = await service.get_message(current_user.organization_id, message_id)
    return OutreachMessageRead.model_validate(message)


@router.patch(
    "/messages/{message_id}",
    response_model=OutreachMessageRead,
    summary="Update a message template",
    dependencies=[Depends(_admin_only)],
)
async def update_message(
    message_id: uuid.UUID,
    body: OutreachMessageUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> OutreachMessageRead:
    service = OutreachService(db)
    message = await service.update_message(
        current_user.organization_id,
        message_id,
        body.model_dump(exclude_unset=True),
    )
    return OutreachMessageRead.model_validate(message)


@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a message template",
    dependencies=[Depends(_admin_only)],
)
async def delete_message(message_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    service = OutreachService(db)
    await service.delete_message(current_user.organization_id, message_id)


# -- attempts -----------------------------------------------------------


@router.get(
    "/leads/{lead_id}/attempts",
    response_model=list[OutreachAttemptRead],
    summary="List outreach attempts for a lead",
)
async def list_lead_attempts(
    lead_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> list[OutreachAttemptRead]:
    service = OutreachService(db)
    attempts = await service.list_attempts_for_lead(current_user.organization_id, lead_id)
    return [OutreachAttemptRead.model_validate(a) for a in attempts]


@router.post(
    "/attempts",
    response_model=OutreachAttemptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an outreach attempt",
)
async def create_attempt(
    body: OutreachAttemptCreate, db: DbSession, current_user: CurrentUser
) -> OutreachAttemptRead:
    service = OutreachService(db)
    data = body.model_dump()
    data["organization_id"] = current_user.organization_id
    attempt = await service.create_attempt(current_user.organization_id, data)
    return OutreachAttemptRead.model_validate(attempt)


@router.patch(
    "/attempts/{attempt_id}",
    response_model=OutreachAttemptRead,
    summary="Update an outreach attempt",
)
async def update_attempt(
    attempt_id: uuid.UUID,
    body: OutreachAttemptUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> OutreachAttemptRead:
    service = OutreachService(db)
    attempt = await service.update_attempt(
        current_user.organization_id,
        attempt_id,
        body.model_dump(exclude_unset=True),
    )
    return OutreachAttemptRead.model_validate(attempt)


# -- follow-ups ---------------------------------------------------------


@router.get(
    "/leads/{lead_id}/follow-ups",
    response_model=list[FollowUpRead],
    summary="List follow-ups for a lead",
)
async def list_lead_follow_ups(
    lead_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> list[FollowUpRead]:
    service = OutreachService(db)
    follow_ups = await service.list_follow_ups_for_lead(current_user.organization_id, lead_id)
    return [FollowUpRead.model_validate(f) for f in follow_ups]


@router.post(
    "/follow-ups",
    response_model=FollowUpRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a follow-up",
)
async def create_follow_up(
    body: FollowUpCreate, db: DbSession, current_user: CurrentUser
) -> FollowUpRead:
    service = OutreachService(db)
    follow_up = await service.create_follow_up(current_user.organization_id, body.model_dump())
    return FollowUpRead.model_validate(follow_up)


@router.patch(
    "/follow-ups/{follow_up_id}",
    response_model=FollowUpRead,
    summary="Update a follow-up",
)
async def update_follow_up(
    follow_up_id: uuid.UUID,
    body: FollowUpUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> FollowUpRead:
    service = OutreachService(db)
    follow_up = await service.update_follow_up(
        current_user.organization_id,
        follow_up_id,
        body.model_dump(exclude_unset=True),
    )
    return FollowUpRead.model_validate(follow_up)


# -- manual queue -------------------------------------------------------


@router.get(
    "/manual",
    response_model=list[ManualOutreachQueueRead],
    summary="List manual outreach tasks",
)
async def list_manual_tasks(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: OutreachStatus | None = Query(default=None, alias="status"),
    assigned_user_id: uuid.UUID | None = None,
) -> list[ManualOutreachQueueRead]:
    service = OutreachService(db)
    tasks = await service.list_manual_tasks(
        current_user.organization_id,
        status=status_filter,
        assigned_user_id=assigned_user_id,
    )
    return [ManualOutreachQueueRead.model_validate(t) for t in tasks]


@router.post(
    "/manual",
    response_model=ManualOutreachQueueRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual outreach task",
)
async def create_manual_task(
    body: ManualOutreachQueueCreate, db: DbSession, current_user: CurrentUser
) -> ManualOutreachQueueRead:
    service = OutreachService(db)
    task = await service.create_manual_task(current_user.organization_id, body.model_dump())
    return ManualOutreachQueueRead.model_validate(task)


@router.get(
    "/manual/{task_id}",
    response_model=ManualOutreachQueueRead,
    summary="Get a manual outreach task",
)
async def get_manual_task(
    task_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> ManualOutreachQueueRead:
    service = OutreachService(db)
    task = await service.get_manual_task(current_user.organization_id, task_id)
    return ManualOutreachQueueRead.model_validate(task)


@router.patch(
    "/manual/{task_id}",
    response_model=ManualOutreachQueueRead,
    summary="Update a manual outreach task",
)
async def update_manual_task(
    task_id: uuid.UUID,
    body: ManualOutreachQueueUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> ManualOutreachQueueRead:
    service = OutreachService(db)
    task = await service.update_manual_task(
        current_user.organization_id,
        task_id,
        body.model_dump(exclude_unset=True),
    )
    return ManualOutreachQueueRead.model_validate(task)
