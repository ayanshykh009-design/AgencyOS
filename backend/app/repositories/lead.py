"""Lead repository: search, filter, dedup-aware creation, soft delete."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, func, or_, select, update
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

    async def get_or_404(self, organization_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
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

    async def list_unassigned(self, organization_id: uuid.UUID, *, limit: int = 500) -> list[Lead]:
        """Return non-deleted leads without an owner (for assignment sweeps)."""
        stmt = (
            select(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.owner_user_id.is_(None),
            )
            .order_by(Lead.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_stages(
        self,
        organization_id: uuid.UUID,
        stage_ids: list[uuid.UUID],
        *,
        limit_per_stage: int = 50,
    ) -> dict[uuid.UUID, list[Lead]]:
        """Return non-deleted leads grouped by stage (newest first), capped."""
        out: dict[uuid.UUID, list[Lead]] = {sid: [] for sid in stage_ids}
        if not stage_ids:
            return out
        stmt = (
            select(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.stage_id.in_(stage_ids),
            )
            .order_by(Lead.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        for lead in result.scalars().all():
            if lead.stage_id is None:
                continue
            bucket = out.get(lead.stage_id)
            if bucket is not None and len(bucket) < limit_per_stage:
                bucket.append(lead)
        return out

    async def count_by_stage(self, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Lead counts per stage (non-deleted only)."""
        stmt = (
            select(Lead.stage_id, func.count(Lead.id))
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.stage_id.is_not(None),
            )
            .group_by(Lead.stage_id)
        )
        result = await self._session.execute(stmt)
        return {stage_id: int(count) for stage_id, count in result.all()}

    async def count_in_stage(self, organization_id: uuid.UUID, stage_id: uuid.UUID) -> int:
        """Count non-deleted leads currently in a stage."""
        stmt = (
            select(func.count(Lead.id))
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.stage_id == stage_id,
            )
            .select_from(Lead)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count_using_close_reason(
        self, organization_id: uuid.UUID, close_reason_id: uuid.UUID
    ) -> int:
        """Count non-deleted leads referencing a close reason."""
        stmt = (
            select(func.count(Lead.id))
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.close_reason_id == close_reason_id,
            )
            .select_from(Lead)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def sum_deal_value(
        self,
        organization_id: uuid.UUID,
        *,
        status: LeadStatus | None = None,
    ) -> Decimal:
        """Sum of ``deal_value`` for non-deleted leads (optionally by status)."""
        stmt = select(func.coalesce(func.sum(Lead.deal_value), 0)).where(
            Lead.organization_id == organization_id,
            Lead.deleted_at.is_(None),
        )
        if status is not None:
            stmt = stmt.where(Lead.status == status)
        result = await self._session.execute(stmt)
        return Decimal(str(result.scalar_one()))

    async def count_unassigned(self, organization_id: uuid.UUID) -> int:
        """Count non-deleted leads without an owner."""
        stmt = (
            select(func.count(Lead.id))
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.owner_user_id.is_(None),
            )
            .select_from(Lead)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def bulk_move_stage(
        self,
        organization_id: uuid.UUID,
        from_stage_id: uuid.UUID,
        to_stage_id: uuid.UUID,
    ) -> int:
        """Move every non-deleted lead out of a stage; returns the count."""
        stmt = (
            update(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.stage_id == from_stage_id,
            )
            .values(stage_id=to_stage_id)
        )
        result = await self._session.execute(stmt)
        return cast(CursorResult, result).rowcount or 0

    async def soft_delete(self, organization_id: uuid.UUID, lead_id: uuid.UUID, *, now) -> bool:
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
