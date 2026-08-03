"""LeadSource repository (tenant-scoped CRUD)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.lead_source import LeadSource


class LeadSourceRepository:
    """Data access for lead sources."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID, source_id: uuid.UUID) -> LeadSource | None:
        stmt = select(LeadSource).where(
            LeadSource.id == source_id,
            LeadSource.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(
        self, organization_id: uuid.UUID, source_id: uuid.UUID
    ) -> LeadSource:
        source = await self.get(organization_id, source_id)
        if source is None or source.organization_id != organization_id:
            raise AppError(
                code="lead_source.not_found",
                message="Lead source not found",
                status_code=404,
            )
        return source

    async def list(
        self, organization_id: uuid.UUID, *, include_inactive: bool = True
    ) -> list[LeadSource]:
        stmt = select(LeadSource).where(
            LeadSource.organization_id == organization_id
        )
        if not include_inactive:
            stmt = stmt.where(LeadSource.is_active.is_(True))
        stmt = stmt.order_by(LeadSource.name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, source: LeadSource) -> None:
        self._session.add(source)

    @staticmethod
    async def handle_integrity_error(exc: IntegrityError) -> None:
        raise AppError(
            code="lead_source.duplicate",
            message="A lead source with that name already exists",
            status_code=409,
        ) from exc
