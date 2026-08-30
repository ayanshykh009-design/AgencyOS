"""Lead service: dedup-aware creation, search, lifecycle transitions.

Pipeline transitions (status/stage/close reason) are delegated to
``PipelineService.reconcile`` so win/loss bookkeeping and activity events
have a single source of truth.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import LeadStatus
from app.models.lead import Lead
from app.repositories.lead import LeadRepository
from app.services.assignment_service import AssignmentService
from app.services.base import commit_with_retry, utcnow
from app.services.pipeline_service import PipelineService


class LeadService:
    """Owns lead business rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._leads = LeadRepository(session)

    # -- reads ----------------------------------------------------------

    async def get(self, organization_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
        return await self._leads.get_or_404(organization_id, lead_id)

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
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Lead], int]:
        leads = await self._leads.search(
            organization_id,
            query=query,
            status=status,
            source_id=source_id,
            owner_user_id=owner_user_id,
            min_score=min_score,
            max_score=max_score,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )
        total = await self._leads.count(
            organization_id,
            query=query,
            status=status,
            source_id=source_id,
            owner_user_id=owner_user_id,
        )
        return leads, total

    async def funnel(self, organization_id: uuid.UUID) -> dict[LeadStatus, int]:
        return await self._leads.funnel(organization_id)

    # -- writes ---------------------------------------------------------

    async def create(self, organization_id: uuid.UUID, data: dict[str, Any]) -> Lead:
        lead = Lead(
            organization_id=organization_id,
            lead_source_id=data.get("lead_source_id"),
            owner_user_id=data.get("owner_user_id"),
            status=data.get("status", LeadStatus.NEW),
            score=data.get("score", 0),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            company=data.get("company"),
            position=data.get("position"),
            location=data.get("location"),
            linkedin_url=data.get("linkedin_url"),
            email=data.get("email"),
            phone=data.get("phone"),
            whatsapp=data.get("whatsapp"),
            website=data.get("website"),
            notes=data.get("notes"),
            deal_value=data.get("deal_value"),
        )
        self._leads.add(lead)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            await self._leads.handle_integrity_error(exc)
        # Reconcile stage/status/timestamps, then auto-assign per org rule.
        await PipelineService(self._session).reconcile(
            organization_id,
            lead,
            status=data.get("status"),
            stage_id=data.get("stage_id"),
            emit_events=False,
        )
        if lead.owner_user_id is None:
            await AssignmentService(self._session).auto_assign(organization_id, lead)
        await commit_with_retry(self._session)
        # Reload so GENERATED/computed columns (email_normalized, etc.) are
        # populated; otherwise async attribute access would lazy-load and raise
        # MissingGreenlet during serialization.
        await self._session.refresh(lead)
        return lead

    async def update(
        self,
        organization_id: uuid.UUID,
        lead_id: uuid.UUID,
        data: dict[str, Any],
    ) -> Lead:
        lead = await self._leads.get_or_404(organization_id, lead_id)
        allowed = {
            "first_name",
            "last_name",
            "company",
            "position",
            "location",
            "linkedin_url",
            "email",
            "phone",
            "whatsapp",
            "website",
            "notes",
            "status",
            "score",
            "lead_source_id",
            "owner_user_id",
            "stage_id",
            "deal_value",
        }
        # Status/stage/close-reason are owned by PipelineService.reconcile, which
        # needs the *original* values to detect bucket transitions (e.g. emit a
        # LEAD_WON activity log). Don't pre-set them here or reconcile will see
        # the new status as the previous one and skip the transition.
        reconciled_keys = ("status", "stage_id", "close_reason_id")
        for field in allowed:
            if field in data and field not in reconciled_keys:
                setattr(lead, field, data[field])
        if any(key in data for key in reconciled_keys):
            await PipelineService(self._session).reconcile(
                organization_id,
                lead,
                status=data.get("status"),
                stage_id=data.get("stage_id"),
                close_reason_id=data.get("close_reason_id"),
                emit_events=True,
            )
        try:
            await commit_with_retry(self._session)
        except IntegrityError as exc:
            await self._session.rollback()
            await self._leads.handle_integrity_error(exc)
        # Reload so GENERATED/computed columns are populated for callers that
        # serialize or read the returned lead.
        await self._session.refresh(lead)
        return lead

    async def soft_delete(self, organization_id: uuid.UUID, lead_id: uuid.UUID) -> None:
        deleted = await self._leads.soft_delete(organization_id, lead_id, now=utcnow())
        if not deleted:
            raise AppError(
                code="lead.not_found",
                message="Lead not found",
                status_code=404,
            )
        await commit_with_retry(self._session)

    # -- helpers --------------------------------------------------------

    async def duplicate_check(
        self,
        organization_id: uuid.UUID,
        *,
        email: str | None = None,
        phone: str | None = None,
        website: str | None = None,
    ) -> list[Lead]:
        """Expose existing leads matching any normalized contact key."""
        from app.schemas.lead import _normalize_domain, _normalize_phone

        return await self._leads.find_duplicates(
            organization_id,
            email_normalized=(email or "").strip().lower() or None,
            phone_normalized=_normalize_phone(phone),
            website_domain=_normalize_domain(website),
        )
