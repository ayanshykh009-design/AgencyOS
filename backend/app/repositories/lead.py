"""Lead repository: search, filter, dedup-aware creation, soft delete."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import LeadStatus
from app.models.lead import Lead

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class LeadRepository:
    """Data access for leads (tenant-scoped, soft-delete aware)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        stmt = select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.id == lead_id,
            Lead.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(
        self, organization_id: uuid.UUID, lead_id: uuid.UUID
    ) -> Lead:
        lead = await self.get(organization_id, lead_id)
        if lead is None:
            raise AppError(
                code="lead.not_found",
                message="Lead not found",
                status_code=404,
            )
        return lead

    def add(self, lead: Lead) -> None:
        self._session.add(lead)

    async def find_duplicates(
        self,
        organization_id: uuid.UUID,
        *,
        email_normalized: str | None = None,
        phone_normalized: str | None = None,
        website_domain: str | None = None,
    ) -> list[Lead]:
        """Find non-deleted leads matching any normalized dedup key."""
        clauses: list[Any] = []
        if email_normalized:
            clauses.append(Lead.email_normalized == email_normalized)
        if phone_normalized:
            clauses.append(Lead.phone_normalized == phone_normalized)
        if website_domain:
            clauses.append(Lead.website_domain == website_domain)
        if not clauses:
            return []
        stmt = (
            select(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                or_(*clauses),
            )
            .limit(20)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        status: LeadStatus | None = None,
        source_id: uuid.UUID | None = None,
        owner_user_id: uuid.UUID | None = None,
        min_score: int | None = None,
        max_score: int | None = None,
        sort: str = "created_at",
        order: str = "desc",
        limit: int = _DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Lead]:
        """Full-text-ish search + facet filtering, org-scoped and paginated."""
        stmt = select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.deleted_at.is_(None),
        )
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Lead.first_name.ilike(like),
                    Lead.last_name.ilike(like),
                    Lead.company.ilike(like),
                    Lead.email.ilike(like),
                    Lead.position.ilike(like),
                )
            )
        if status is not None:
            stmt = stmt.where(Lead.status == status)
        if source_id is not None:
            stmt = stmt.where(Lead.lead_source_id == source_id)
        if owner_user_id is not None:
            stmt = stmt.where(Lead.owner_user_id == owner_user_id)
        if min_score is not None:
            stmt = stmt.where(Lead.score >= min_score)
        if max_score is not None:
            stmt = stmt.where(Lead.score <= max_score)

        column = getattr(Lead, sort, Lead.created_at)
        order_col = column.desc() if order == "desc" else column.asc()
        stmt = stmt.order_by(order_col).limit(min(limit, _MAX_PAGE_SIZE)).offset(offset)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        organization_id: uuid.UUID,
        *,
        query: str | None = None,
        status: LeadStatus | None = None,
        source_id: uuid.UUID | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> int:
        """Count leads matching the same filters as :meth:`search`."""
        stmt = (
            select(func.count(Lead.id))
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
            )
            .select_from(Lead)
        )
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Lead.first_name.ilike(like),
                    Lead.last_name.ilike(like),
                    Lead.company.ilike(like),
                    Lead.email.ilike(like),
                    Lead.position.ilike(like),
                )
            )
        if status is not None:
            stmt = stmt.where(Lead.status == status)
        if source_id is not None:
            stmt = stmt.where(Lead.lead_source_id == source_id)
        if owner_user_id is not None:
            stmt = stmt.where(Lead.owner_user_id == owner_user_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def funnel(self, organization_id: uuid.UUID) -> dict[LeadStatus, int]:
        """Lead counts grouped by lifecycle status (for dashboards)."""
        stmt = (
            select(Lead.status, func.count(Lead.id))
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
            )
            .group_by(Lead.status)
        )
        result = await self._session.execute(stmt)
        return {status: int(count) for status, count in result.all()}

    async def soft_delete(
        self, organization_id: uuid.UUID, lead_id: uuid.UUID, *, now
    ) -> bool:
        """Soft-delete a lead; returns False when it does not exist."""
        lead = await self.get(organization_id, lead_id)
        if lead is None:
            return False
        lead.deleted_at = now
        return True

    @staticmethod
    async def handle_integrity_error(exc: IntegrityError) -> None:
        """Map unique-constraint violations to a duplicate-lead 409."""
        raise AppError(
            code="lead.duplicate",
            message="A lead with the same email/phone/website already exists",
            status_code=409,
        ) from exc
