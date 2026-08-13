"""Organization service."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.organization import Organization
from app.repositories.organization import OrganizationRepository
from app.services.base import commit_with_retry


class OrganizationService:
    """Owns organization business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._orgs = OrganizationRepository(session)

    async def get(self, organization_id: uuid.UUID) -> Organization:
        organization = await self._orgs.get(organization_id)
        if organization is None:
            raise AppError(
                code="organization.not_found",
                message="Organization not found",
                status_code=404,
            )
        return organization

    async def update_settings(
        self, organization_id: uuid.UUID, settings_update: dict
    ) -> Organization:
        await self.get(organization_id)
        organization = await self._orgs.update_settings(organization_id, settings_update)
        await commit_with_retry(self._session)
        assert organization is not None
        return organization
