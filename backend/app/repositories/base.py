"""Generic tenant-scoped repository.

AgencyOS is a multi-tenant system: nearly every row belongs to exactly one
organization. This base enforces that invariant in one place — every query is
scoped by ``organization_id`` — so domain repositories cannot accidentally
leak rows across tenants.

Repositories are constructed with an :class:`AsyncSession` and never commit;
services own the transaction boundary (commit/rollback + retries).
"""
from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository(Generic[ModelT]):
    """CRUD scoped to a single organization for a single model."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    # -- reads ---------------------------------------------------------

    async def get(
        self, organization_id: uuid.UUID, entity_id: uuid.UUID
    ) -> ModelT | None:
        """Fetch one entity within an organization, or None."""
        stmt = select(self._model).where(
            self._model.organization_id == organization_id,  # type: ignore[attr-defined]
            self._model.id == entity_id,  # type: ignore[attr-defined]
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        order_by: Any | None = None,
    ) -> list[ModelT]:
        """List entities within an organization with pagination."""
        stmt = select(self._model).where(
            self._model.organization_id == organization_id  # type: ignore[attr-defined]
        )
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, organization_id: uuid.UUID) -> int:
        """Count entities within an organization."""
        stmt = (
            select(self._model.id)  # type: ignore[attr-defined]
            .where(self._model.organization_id == organization_id)  # type: ignore[attr-defined]
            .order_by(None)
        )
        result = await self._session.execute(stmt)
        return len(result.all())

    # -- writes --------------------------------------------------------

    def add(self, instance: ModelT) -> None:
        """Queue an instance for insertion (flushed by the service)."""
        self._session.add(instance)

    async def delete(
        self, organization_id: uuid.UUID, entity_id: uuid.UUID
    ) -> bool:
        """Delete one entity; returns False when it does not exist."""
        instance = await self.get(organization_id, entity_id)
        if instance is None:
            return False
        await self._session.delete(instance)
        return True

    # -- convenience ----------------------------------------------------

    async def get_or_404(
        self, organization_id: uuid.UUID, entity_id: uuid.UUID
    ) -> ModelT:
        """Fetch an entity or raise the standard not-found error."""
        from app.core.errors import AppError

        instance = await self.get(organization_id, entity_id)
        if instance is None:
            raise AppError(
                code=f"{self._model.__tablename__}.not_found",
                message=f"{self._model.__name__} not found",
                status_code=404,
            )
        return instance

    async def flush(self) -> None:
        """Flush pending changes so server defaults/GENERATED columns load."""
        await self._session.flush()

    async def refresh(self, instance: ModelT) -> None:
        """Reload an instance from the database (e.g. after a flush)."""
        try:
            await self._session.refresh(instance)
        except NoResultFound:  # pragma: no cover - defensive
            pass
