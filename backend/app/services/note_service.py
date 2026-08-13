"""Note service: lead-scoped commentary with an activity trail.

Notes are always attached to a lead; every create/update/delete mirrors into
the activity trail (NOTE_CREATED / NOTE_UPDATED / NOTE_DELETED) so note
timelines are auditable and reconstructible per lead.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.activity_log import ActivityLog
from app.models.enums import ActivityEventType
from app.models.note import Note
from app.models.user import User
from app.repositories.activity_log import ActivityLogRepository
from app.repositories.lead import LeadRepository
from app.repositories.note import NoteRepository
from app.services.base import commit_with_retry, utcnow


class NoteService:
    """Owns note business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notes = NoteRepository(session)
        self._leads = LeadRepository(session)
        self._activity = ActivityLogRepository(session)

    async def list_by_lead(
        self,
        organization_id: uuid.UUID,
        lead_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Note]:
        await self._leads.get_or_404(organization_id, lead_id)
        return await self._notes.list_by_lead(organization_id, lead_id, limit=limit, offset=offset)

    async def get(self, organization_id: uuid.UUID, note_id: uuid.UUID) -> Note:
        return await self._notes.get_or_404(organization_id, note_id)

    async def create(
        self,
        organization_id: uuid.UUID,
        actor: User,
        *,
        lead_id: uuid.UUID,
        body: str,
        pinned: bool = False,
    ) -> Note:
        body = self._clean_body(body)
        await self._leads.get_or_404(organization_id, lead_id)
        note = Note(
            organization_id=organization_id,
            lead_id=lead_id,
            author_user_id=actor.id,
            body=body,
            pinned=pinned,
        )
        self._notes.add(note)
        self._activity.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id,
                lead_id=lead_id,
                event_type=ActivityEventType.NOTE_CREATED,
                entity_type="note",
                entity_id=note.id,
                description="Note created",
                metadata_={"pinned": pinned},
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)
        return note

    async def update(
        self,
        organization_id: uuid.UUID,
        actor: User,
        note_id: uuid.UUID,
        *,
        body: str | None = None,
        pinned: bool | None = None,
    ) -> Note:
        note = await self._notes.get_or_404(organization_id, note_id)
        changed = False
        if body is not None:
            note.body = self._clean_body(body)
            changed = True
        if pinned is not None and note.pinned is not pinned:
            note.pinned = pinned
            changed = True
        if changed:
            self._activity.add(
                ActivityLog(
                    organization_id=organization_id,
                    user_id=actor.id,
                    lead_id=note.lead_id,
                    event_type=ActivityEventType.NOTE_UPDATED,
                    entity_type="note",
                    entity_id=note.id,
                    description="Note updated",
                    metadata_={"pinned": note.pinned},
                    occurred_at=utcnow(),
                )
            )
        await commit_with_retry(self._session)
        return note

    async def delete(self, organization_id: uuid.UUID, actor: User, note_id: uuid.UUID) -> None:
        note = await self._notes.get_or_404(organization_id, note_id)
        await self._notes.delete(note)
        self._activity.add(
            ActivityLog(
                organization_id=organization_id,
                user_id=actor.id,
                lead_id=note.lead_id,
                event_type=ActivityEventType.NOTE_DELETED,
                entity_type="note",
                entity_id=note.id,
                description="Note deleted",
                metadata_={},
                occurred_at=utcnow(),
            )
        )
        await commit_with_retry(self._session)

    @staticmethod
    def _clean_body(body: str) -> str:
        cleaned = body.strip()
        if not cleaned:
            raise AppError(
                code="note.body_required",
                message="Note body is required",
                status_code=400,
            )
        return cleaned
