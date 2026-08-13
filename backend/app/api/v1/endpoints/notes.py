"""Note endpoints: lead-scoped commentary CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.permissions import Permission, require_permission
from app.schemas.common import Page
from app.schemas.note import NoteCreate, NoteRead, NoteUpdate
from app.services.note_service import NoteService

router = APIRouter()

_read = Depends(require_permission(Permission.NOTE_READ))
_write = Depends(require_permission(Permission.NOTE_WRITE))


@router.get(
    "",
    response_model=Page[NoteRead],
    summary="List notes for a lead (pinned first)",
    dependencies=[_read],
)
async def list_notes(
    db: DbSession,
    current_user: CurrentUser,
    lead_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[NoteRead]:
    service = NoteService(db)
    notes = await service.list_by_lead(
        current_user.organization_id, lead_id, limit=limit, offset=offset
    )
    return Page(
        items=[NoteRead.model_validate(n) for n in notes],
        total=len(notes),
    )


@router.post(
    "",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a note on a lead",
    dependencies=[_write],
)
async def create_note(
    body: NoteCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> NoteRead:
    service = NoteService(db)
    note = await service.create(
        current_user.organization_id,
        current_user,
        lead_id=body.lead_id,
        body=body.body,
        pinned=body.pinned,
    )
    return NoteRead.model_validate(note)


@router.get(
    "/{note_id}",
    response_model=NoteRead,
    summary="Get a note",
    dependencies=[_read],
)
async def get_note(
    note_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> NoteRead:
    service = NoteService(db)
    note = await service.get(current_user.organization_id, note_id)
    return NoteRead.model_validate(note)


@router.patch(
    "/{note_id}",
    response_model=NoteRead,
    summary="Update a note",
    dependencies=[_write],
)
async def update_note(
    note_id: uuid.UUID,
    body: NoteUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> NoteRead:
    service = NoteService(db)
    note = await service.update(
        current_user.organization_id,
        current_user,
        note_id,
        body=body.body,
        pinned=body.pinned,
    )
    return NoteRead.model_validate(note)


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a note",
    dependencies=[_write],
)
async def delete_note(note_id: uuid.UUID, db: DbSession, current_user: CurrentUser):
    service = NoteService(db)
    await service.delete(current_user.organization_id, current_user, note_id)
