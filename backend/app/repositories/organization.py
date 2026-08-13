"""Organization repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.organization import Organization


class OrganizationRepository:
    """Data access for organizations (tenants)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID) -> Organization | None:
        return await self._session.get(Organization, organization_id)

    async def list_ids(self) -> list[uuid.UUID]:
        """Return all organization ids (system-level, used by background workers)."""
        result = await self._session.execute(select(Organization.id))
        return list(result.scalars().all())

    async def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, organization: Organization) -> None:
        self._session.add(organization)

    async def update_settings(
        self, organization_id: uuid.UUID, settings: dict
    ) -> Organization | None:
        organization = await self.get(organization_id)
        if organization is None:
            return None
        merged = dict(organization.settings or {})
        merged.update(settings)
        organization.settings = merged
        return organization

    async def ensure_slug_available(self, slug: str) -> None:
        """Raise a 409 when a slug is already taken (conflict)."""
        existing = await self.get_by_slug(slug)
        if existing is not None:
            raise AppError(
                code="organization.slug_taken",
                message="An organization with that slug already exists",
                status_code=409,
            )

    @staticmethod
    async def handle_integrity_error(exc: IntegrityError) -> None:
        """Map a duplicate-slug integrity error to a friendly 409."""
        raise AppError(
            code="organization.slug_taken",
            message="An organization with that slug already exists",
            status_code=409,
        ) from exc
