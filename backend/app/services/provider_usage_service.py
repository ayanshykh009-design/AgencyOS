"""ProviderUsage service: record and aggregate AI/provider usage."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_usage import ProviderUsage
from app.repositories.provider_usage import ProviderUsageRepository
from app.services.base import commit_with_retry


class ProviderUsageService:
    """Owns usage rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._usage = ProviderUsageRepository(session)

    async def record(
        self,
        organization_id: uuid.UUID,
        *,
        provider: str,
        feature: str,
        usage_date: date,
        request_count: int = 1,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._usage.upsert_daily(
            organization_id,
            provider=provider,
            feature=feature,
            usage_date=usage_date,
            request_count=request_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            metadata=metadata,
        )
        await commit_with_retry(self._session)

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProviderUsage]:
        return await self._usage.list(
            organization_id, provider=provider, limit=limit, offset=offset
        )

    async def totals_since(
        self, organization_id: uuid.UUID, *, since: datetime
    ) -> dict[str, float | int]:
        return await self._usage.totals_since(organization_id, since=since)

    async def spend_last_30_days(self, organization_id: uuid.UUID) -> float:
        return await self._usage.spend_last_30_days(organization_id)
