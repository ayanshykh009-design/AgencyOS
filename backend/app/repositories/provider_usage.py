"""ProviderUsage repository: daily rollups + aggregation."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_usage import ProviderUsage


class ProviderUsageRepository:
    """Data access for AI/provider usage accounting."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_daily(
        self,
        organization_id: uuid.UUID,
        *,
        provider: str,
        feature: str,
        usage_date: date,
    ) -> ProviderUsage | None:
        stmt = select(ProviderUsage).where(
            ProviderUsage.organization_id == organization_id,
            ProviderUsage.provider == provider,
            ProviderUsage.feature == feature,
            ProviderUsage.usage_date == usage_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProviderUsage]:
        stmt = select(ProviderUsage).where(ProviderUsage.organization_id == organization_id)
        if provider is not None:
            stmt = stmt.where(ProviderUsage.provider == provider)
        stmt = stmt.order_by(ProviderUsage.usage_date.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_daily(
        self,
        organization_id: uuid.UUID,
        *,
        provider: str,
        feature: str,
        usage_date: date,
        request_count: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        metadata: dict | None = None,
    ) -> None:
        """Increment the daily rollup for a provider/feature (atomic upsert)."""
        stmt = insert(ProviderUsage).values(
            organization_id=organization_id,
            provider=provider,
            feature=feature,
            usage_date=usage_date,
            request_count=request_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            metadata=metadata or {},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                ProviderUsage.organization_id,
                ProviderUsage.provider,
                ProviderUsage.feature,
                ProviderUsage.usage_date,
            ],
            set_={
                "request_count": ProviderUsage.request_count + request_count,
                "input_tokens": ProviderUsage.input_tokens + input_tokens,
                "output_tokens": ProviderUsage.output_tokens + output_tokens,
                "cost_usd": ProviderUsage.cost_usd + cost_usd,
            },
        )
        await self._session.execute(stmt)

    async def totals_since(
        self,
        organization_id: uuid.UUID,
        *,
        since: datetime,
        feature_prefix: str | None = None,
    ) -> dict[str, float | int]:
        """Aggregate request/token/cost totals since a cutoff.

        ``feature_prefix`` narrows the rollup to features whose name starts with
        the prefix (e.g. ``"ai."`` for all AI-run execution), enabling the M11-B
        per-org budget to cover every provider under one cumulative ceiling.
        """
        conditions = [
            ProviderUsage.organization_id == organization_id,
            ProviderUsage.usage_date >= since.date(),
        ]
        if feature_prefix:
            conditions.append(ProviderUsage.feature.like(f"{feature_prefix}%"))
        stmt = (
            select(
                func.sum(ProviderUsage.request_count),
                func.sum(ProviderUsage.input_tokens),
                func.sum(ProviderUsage.output_tokens),
                func.sum(ProviderUsage.cost_usd),
            )
            .where(*conditions)
            .select_from(ProviderUsage)
        )
        result = await self._session.execute(stmt)
        row = result.one()
        return {
            "requests": int(row[0] or 0),
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "cost_usd": float(row[3] or 0),
        }

    async def spend_last_30_days(self, organization_id: uuid.UUID) -> float:
        cutoff = datetime.now().date() - timedelta(days=30)
        totals = await self.totals_since(
            organization_id, since=datetime.combine(cutoff, datetime.min.time())
        )
        return float(totals["cost_usd"])
