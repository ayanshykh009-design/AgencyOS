"""Inbound webhook endpoints (no user session).

Used by external systems (n8n workflows, contact forms) to push leads into
AgencyOS. Authenticated with a shared secret via the ``X-AgencyOS-Webhook``
header; refuses to operate when ``WEBHOOK_SECRET`` is unset.

When a shared secret is configured, requests must also carry:

- ``X-AgencyOS-Timestamp`` — Unix timestamp in seconds.
- ``X-AgencyOS-Nonce`` — 8–128 URL-safe characters (``A-Za-z0-9_-``).
- ``X-AgencyOS-Signature`` — lowercase-or-uppercase hex HMAC-SHA256.

Exact signature scheme: ``hex(HMAC_SHA256(WEBHOOK_SECRET, message))`` where
``message`` is the UTF-8 bytes of ``"<timestamp>.<nonce>."`` followed by the
**exact raw request body bytes** (no JSON re-serialization). The timestamp is
bounded by ``WEBHOOK_TIMESTAMP_SKEW_SECONDS`` and the nonce is single-use for
``WEBHOOK_REPLAY_TTL_SECONDS``. Failures are always reported through the
unified ``AppError`` envelope and never include secrets or signatures.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import threading
import time
import uuid

from fastapi import APIRouter, Header, Request

from app.api.deps import DbSession
from app.core.config import settings
from app.core.errors import AppError
from app.core.redis import get_redis
from app.core.tenant_context import activate_org
from app.repositories.organization import OrganizationRepository
from app.schemas.lead import LeadBase
from app.services.lead_service import LeadService

router = APIRouter()

_TIMESTAMP_RE = re.compile(r"^[0-9]{1,20}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REPLAY_KEY_PREFIX = "agencyos:webhook:replay:v1"
_REPLAY_KEY_DOMAIN = b"agencyos:inbound-webhook-replay:v1"
_MAX_MEMORY_REPLAY_KEYS = 4096
# Bounded process-local replay state, used ONLY in explicit local environments.
_replay_seen: dict[str, float] = {}
_replay_claims: dict[str, str] = {}
_replay_lock = threading.Lock()
_logger = logging.getLogger("agencyos.webhooks")
_RELEASE_REPLAY_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


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


def _invalid_signature() -> AppError:
    """Uniform, non-revealing error for every signature/header failure."""
    return AppError(
        code="webhook.invalid_signature",
        message="Invalid webhook signature",
        status_code=401,
    )


def _verify_signature(
    timestamp: str | None,
    nonce: str | None,
    signature: str | None,
    raw_body: bytes,
) -> None:
    """Verify the documented HMAC scheme over the untouched request body."""
    if (
        not timestamp
        or not nonce
        or not signature
        or not _TIMESTAMP_RE.fullmatch(timestamp)
        or not _NONCE_RE.fullmatch(nonce)
        or not _SIGNATURE_RE.fullmatch(signature)
    ):
        raise _invalid_signature()
    try:
        skew = abs(time.time() - int(timestamp))
    except (ValueError, OverflowError):
        raise _invalid_signature() from None
    if skew > settings.WEBHOOK_TIMESTAMP_SKEW_SECONDS:
        raise _invalid_signature()

    signed = timestamp.encode("ascii") + b"." + nonce.encode("ascii") + b"." + raw_body
    expected = hmac.new(
        settings.WEBHOOK_SECRET.encode("utf-8"), signed, hashlib.sha256
    ).hexdigest()
    if not secrets.compare_digest(signature.lower(), expected):
        raise _invalid_signature()


def _replay_key(organization_slug: str, nonce: str) -> str:
    """Opaque domain-separated key scoped by organization slug and nonce."""
    material = (
        _REPLAY_KEY_DOMAIN
        + b"\x00"
        + organization_slug.encode("utf-8")
        + b"\x00"
        + nonce.encode("ascii")
    )
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), material, hashlib.sha256
    ).hexdigest()
    return f"{_REPLAY_KEY_PREFIX}:{digest}"


async def _reserve_replay(
    organization_slug: str, nonce: str, claim: str | None = None
) -> bool:
    """Atomically consume one nonce. False means replay; store failure fails closed."""
    global _replay_seen
    key = _replay_key(organization_slug, nonce)
    ttl = settings.WEBHOOK_REPLAY_TTL_SECONDS
    claim = claim or secrets.token_hex(16)

    if settings.is_local_environment:
        now = time.monotonic()
        with _replay_lock:
            expiry = _replay_seen.get(key)
            if expiry is not None and expiry > now:
                return False
            if len(_replay_seen) >= _MAX_MEMORY_REPLAY_KEYS:
                for stale_key in [k for k, v in _replay_seen.items() if v <= now]:
                    del _replay_seen[stale_key]
                    _replay_claims.pop(stale_key, None)
                while len(_replay_seen) >= _MAX_MEMORY_REPLAY_KEYS:
                    oldest = min(_replay_seen, key=_replay_seen.__getitem__)
                    del _replay_seen[oldest]
                    _replay_claims.pop(oldest, None)
            _replay_seen[key] = now + ttl
            _replay_claims[key] = claim
            return True

    # Deployed environments: shared Redis only. Never degrade to process memory.
    try:
        acquired = await get_redis().set(key, claim, nx=True, ex=ttl)
    except Exception as exc:
        raise AppError(
            code="webhook.replay_unavailable",
            message="Webhook replay guard unavailable",
            status_code=503,
        ) from exc
    return bool(acquired)


async def _release_replay(organization_slug: str, nonce: str, claim: str) -> None:
    """Undo a reservation when ingestion fails after the nonce was consumed.

    The claim token prevents a delayed release from deleting a newer successful
    delivery that reused the same nonce after this reservation expired.
    """
    key = _replay_key(organization_slug, nonce)

    if settings.is_local_environment:
        now = time.monotonic()
        with _replay_lock:
            expiry = _replay_seen.get(key)
            if expiry is None or expiry <= now:
                return
            if _replay_claims.get(key) == claim:
                del _replay_seen[key]
                _replay_claims.pop(key, None)
        return

    try:
        await get_redis().eval(_RELEASE_REPLAY_SCRIPT, 1, key, claim)
    except Exception:
        # Never mask the original ingestion error. The nonce stays consumed for
        # its short TTL, which is the fail-closed behaviour for replay state.
        _logger.warning("Failed to release webhook replay reservation")


@router.post(
    "/leads",
    response_model=dict,
    status_code=201,
    summary="Ingest a lead from an external system",
)
async def ingest_lead(
    request: Request,
    body: WebhookLeadBody,
    db: DbSession,
    x_agencyos_webhook: str | None = Header(default=None, alias="X-AgencyOS-Webhook"),
    x_agencyos_timestamp: str | None = Header(
        default=None, alias="X-AgencyOS-Timestamp"
    ),
    x_agencyos_nonce: str | None = Header(default=None, alias="X-AgencyOS-Nonce"),
    x_agencyos_signature: str | None = Header(
        default=None, alias="X-AgencyOS-Signature"
    ),
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

    # Read the exact bytes that arrived on the wire; Pydantic parsing above is
    # for field validation only and must not be re-serialized for verification.
    raw_body = await request.body()
    _verify_signature(
        x_agencyos_timestamp, x_agencyos_nonce, x_agencyos_signature, raw_body
    )
    claim = secrets.token_hex(16)
    if not await _reserve_replay(body.organization_slug, x_agencyos_nonce or "", claim):
        raise AppError(
            code="webhook.replay_detected",
            message="Duplicate webhook delivery",
            status_code=409,
        )

    try:
        # No authenticated user on this route, so bind the tenant context here:
        # every LeadService write below is org-scoped by the RLS policies.
        await activate_org(db, organization.id)

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
    except Exception:
        # A failed delivery must not burn the nonce: a sender retrying after a
        # transient error needs to be able to complete the same delivery.
        await _release_replay(body.organization_slug, x_agencyos_nonce or "", claim)
        raise
