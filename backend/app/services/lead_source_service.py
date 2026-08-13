"""LeadSource service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OutreachChannel
from app.models.lead_source import LeadSource
from app.repositories.lead_source import LeadSourceRepository
from app.services.base import commit_with_retry


class LeadSourceService:
    """Owns lead-source rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sources = LeadSourceRepository(session)

    async def list(
        self, organization_id: uuid.UUID, *, include_inactive: bool = True
    ) -> list[LeadSource]:
        return await self._sources.list(organization_id, include_inactive=include_inactive)

    async def get(self, organization_id: uuid.UUID, source_id: uuid.UUID) -> LeadSource:
        return await self._sources.get_or_404(organization_id, source_id)

    async def create(self, organization_id: uuid.UUID, data: dict[str, Any]) -> LeadSource:
        source = LeadSource(
            organization_id=organization_id,
            name=data["name"],
            channel=OutreachChannel(data.get("channel", "contact_form")),
            description=data.get("description"),
            is_active=bool(data.get("is_active", True)),
        )
        self._sources.add(source)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            await self._sources.handle_integrity_error(exc)
        await commit_with_retry(self._session)
        return source

    async def update(
        self,
        organization_id: uuid.UUID,
        source_id: uuid.UUID,
        data: dict[str, Any],
    ) -> LeadSource:
        source = await self._sources.get_or_404(organization_id, source_id)
        if "name" in data:
            source.name = data["name"]
        if "channel" in data:
            source.channel = OutreachChannel(data["channel"])
        if "description" in data:
            source.description = data["description"]
        if "is_active" in data:
            source.is_active = bool(data["is_active"])
        try:
            await commit_with_retry(self._session)
        except IntegrityError as exc:
            await self._session.rollback()
            await self._sources.handle_integrity_error(exc)
        return source
