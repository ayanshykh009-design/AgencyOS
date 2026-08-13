"""Inbound webhook endpoints (no user session).

Used by external systems (n8n workflows, contact forms) to push leads into
AgencyOS. Authenticated with a shared secret via the ``X-AgencyOS-Webhook``
header; refuses to operate when ``WEBHOOK_SECRET`` is unset.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Header

from app.api.deps import DbSession
from app.core.config import settings
from app.core.errors import AppError
from app.repositories.organization import OrganizationRepository
from app.schemas.lead import LeadBase
from app.services.lead_service import LeadService

router = APIRouter()


class WebhookLeadBody(LeadBase):
    """Lead payload accepted from webhooks (org resolved from slug)."""

    lead_source_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    organization_slug: str | None = None


def _check_secret(secret: str | None) -> None:
    if not settings.WEBHOOK_SECRET:
        raise AppError(
            code="webhook.not_configured",
            message="Webhooks are not configured on this deployment",
            status_code=503,
        )
    provided = secret or ""
    if not secrets.compare_digest(provided.encode(), settings.WEBHOOK_SECRET.encode()):
        raise AppError(
            code="webhook.invalid_secret",
            message="Invalid webhook secret",
            status_code=401,
        )


@router.post(
    "/leads",
    response_model=dict,
    status_code=201,
    summary="Ingest a lead from an external system",
)
async def ingest_lead(
    body: WebhookLeadBody,
    db: DbSession,
    x_agencyos_webhook: str | None = Header(default=None, alias="X-AgencyOS-Webhook"),
) -> dict:
    """Create a lead idempotently: returns the existing lead when duplicated."""
    _check_secret(x_agencyos_webhook)

    if not body.organization_slug:
        raise AppError(
            code="webhook.missing_org",
            message="organization_slug is required",
            status_code=400,
        )
    organization = await OrganizationRepository(db).get_by_slug(body.organization_slug)
    if organization is None:
        raise AppError(
            code="webhook.unknown_org",
            message="Unknown organization_slug",
            status_code=404,
        )

    service = LeadService(db)
    data = body.model_dump(exclude={"organization_slug", "organization_id"})
    data["organization_id"] = organization.id

    duplicates = await service.duplicate_check(
        organization.id,
        email=data.get("email"),
        phone=data.get("phone"),
        website=data.get("website"),
    )
    if duplicates:
        return {"lead_id": str(duplicates[0].id), "duplicate": True}

    lead = await service.create(organization.id, data)
    return {"lead_id": str(lead.id), "duplicate": False}
