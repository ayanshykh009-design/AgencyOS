"""Search service: combines org-scoped text search across domain objects."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.note import Note
from app.models.task import Task
from app.repositories.lead import LeadRepository
from app.repositories.note import NoteRepository
from app.repositories.task import TaskRepository


class SearchService:
    """Fans a query out to leads, tasks, and notes within one organization."""

    def __init__(self, session: AsyncSession) -> None:
        self._leads = LeadRepository(session)
        self._tasks = TaskRepository(session)
        self._notes = NoteRepository(session)

    async def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str,
        limit: int = 10,
    ) -> dict:
        """Run the query against each store and return per-type result lists."""
        leads, tasks, notes = await self._search_all(
            organization_id, query=query, limit=limit
        )
        return {
            "query": query,
            "leads": leads,
            "tasks": tasks,
            "notes": notes,
            "counts": {
                "leads": len(leads),
                "tasks": len(tasks),
                "notes": len(notes),
                "total": len(leads) + len(tasks) + len(notes),
            },
        }

    async def _search_all(
        self,
        organization_id: uuid.UUID,
        *,
        query: str,
        limit: int,
    ) -> tuple[list[Lead], list[Task], list[Note]]:
        """Run the query against each store (sequential: one shared session)."""
        leads = await self._leads.search(organization_id, query=query, limit=limit)
        tasks = await self._tasks.search_tasks(organization_id, query=query, limit=limit)
        notes = await self._notes.search(organization_id, query=query, limit=limit)
        return leads, tasks, notes
