"""Resolve an organization's effective LLM provider/model.

Per-org overrides stored in ``organizations.settings.ai`` take precedence; the
env defaults (``LLM_PROVIDER`` / ``LLM_DEFAULT_MODEL``) are the fallback.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.repositories.organization import OrganizationRepository

SUPPORTED_PROVIDERS = (
    "openai",
    "anthropic",
    "gemini",
    "openai-compatible",
    "ollama",
    "deepseek",
)


async def resolve_ai_config(
    session: AsyncSession, organization_id: uuid.UUID
) -> tuple[str, str | None]:
    """Return ``(provider, model)`` honoring per-org settings over env defaults."""
    org = await OrganizationRepository(session).get(organization_id)
    ai: dict[str, Any] = {}
    if org is not None and isinstance(org.settings, dict):
        stored = org.settings.get("ai")
        if isinstance(stored, dict):
            ai = stored

    provider = ai.get("provider") or settings.LLM_PROVIDER
    model = ai.get("model") or settings.LLM_DEFAULT_MODEL
    if not isinstance(provider, str) or provider not in SUPPORTED_PROVIDERS:
        raise AppError(
            code="ai.invalid_provider",
            message=f"unsupported LLM provider: {provider!r}",
            status_code=400,
        )
    return provider, model
