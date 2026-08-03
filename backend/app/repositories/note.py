"""Note repository: org-scoped data access for lead notes."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.note import Note


class NoteRepository:
    """Data access for notes (tenant-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, note: Note) -> None:
        self._session.add(note)

    async def delete(self, note: Note) -> None:
        await self._session.delete(note)

    async def get(self, organization_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
        stmt = select(Note).where(
            Note.organization_id == organization_id,
            Note.id == note_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(
        self, organization_id: uuid.UUID, note_id: uuid.UUID
    ) -> Note:
        note = await self.get(organization_id, note_id)
        if note is None:
            raise AppError(
                code="note.not_found",
                message="Note not found",
                status_code=404,
            )
        return note

    async def list_by_lead(
        self,
        organization_id: uuid.UUID,
        lead_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Note]:
        """Return a lead's notes, pinned first then newest first."""
        stmt = (
            select(Note)
            .where(
                Note.organization_id == organization_id,
                Note.lead_id == lead_id,
            )
            .order_by(Note.pinned.desc(), Note.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_lead(
        self, organization_id: uuid.UUID, lead_id: uuid.UUID
    ) -> int:
        stmt = (
            select(func.count(Note.id))
            .where(Note.organization_id == organization_id, Note.lead_id == lead_id)
            .select_from(Note)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Note]:
        """Return notes whose body matches ``query``, newest first."""
        like = f"%{query}%"
        stmt = (
            select(Note)
            .where(
                Note.organization_id == organization_id,
                Note.body.ilike(like),
            )
            .order_by(Note.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
