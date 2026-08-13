"""Growth agent executor — M7 deterministic growth intelligence.

Unlike the brain-backed executors, the growth agent does not require an LLM:
it runs the deterministic M7 engines over an org-scoped snapshot and persists
analyses (``growth_analyses``), evidence-backed recommendations, and forecasts.
This keeps growth reporting reproducible and LLM-free; narration is optional.

Run input (dict):
* ``analysis_type`` — one of the :class:`GrowthAnalysisType` values, or ``full``
  (default) to run every engine and persist one snapshot per type.
* ``period_start`` / ``period_end`` — ISO-8601 window (defaults to last 30 days).
* ``goal`` — accepted for parity with other agents; unused by the engine.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.agents.executors.base import ExecutorContext, ExecutorResult
from app.agents.executors.registry import register_executor
from app.core.config import settings
from app.models.enums import GrowthAnalysisType
from app.services.growth_analytics_service import GrowthAnalyticsService

_VALID_TYPES = tuple(item.value for item in GrowthAnalysisType)


class GrowthAgentExecutor:
    """Runs the deterministic growth engines and persists the snapshots."""

    name = "growth_agent"
    description = (
        "You run deterministic growth intelligence: KPIs, pipeline, funnel, "
        "conversion, revenue, activity, bottlenecks, opportunities, trends, "
        "health scoring, forecasts, and what-if scenarios for the organization."
    )

    async def execute(self, ctx: ExecutorContext) -> ExecutorResult:
        if not settings.GROWTH_AGENT_ENABLED:
            return ExecutorResult(
                success=False,
                error="Growth agent is disabled (GROWTH_AGENT_ENABLED=false)",
            )

        service = GrowthAnalyticsService(ctx.session)
        period_end = self._parse_period(ctx.input.get("period_end"), default=None)
        period_start = self._parse_period(
            ctx.input.get("period_start"),
            default=(period_end or datetime.utcnow()) - timedelta(days=30),
        )
        period_end = period_end or datetime.utcnow()
        analysis_type = str(ctx.input.get("analysis_type") or "full")

        try:
            if analysis_type == "full":
                return await self._run_full(service, ctx, period_start, period_end)
            if analysis_type in _VALID_TYPES:
                return await self._run_single(
                    service, ctx, GrowthAnalysisType(analysis_type), period_start, period_end
                )
            return ExecutorResult(
                success=False,
                error=(
                    f"unknown analysis_type {analysis_type!r}; expected 'full' or one of "
                    f"{', '.join(_VALID_TYPES)}"
                ),
            )
        except Exception as exc:  # noqa: BLE001 - sanitized by the runtime
            return ExecutorResult(success=False, error=f"growth analysis failed: {exc}")

    async def _run_full(
        self,
        service: GrowthAnalyticsService,
        ctx: ExecutorContext,
        period_start: datetime,
        period_end: datetime,
    ) -> ExecutorResult:
        analyses = await service.run_full_analysis(
            ctx.organization_id,
            period_start=period_start,
            period_end=period_end,
            generated_by="growth_agent",
        )
        completed = [analysis for analysis in analyses if analysis.status.value == "completed"]
        health = next(
            (
                analysis
                for analysis in completed
                if analysis.analysis_type == GrowthAnalysisType.HEALTH
            ),
            None,
        )
        counts: dict[str, int] = {}
        for analysis in completed:
            key = analysis.analysis_type.value
            counts[key] = counts.get(key, 0) + 1

        recommendations = await service.list_recommendations(
            ctx.organization_id, status=None, priority=None, limit=100
        )
        return ExecutorResult(
            success=True,
            output={
                "ran_analysis_types": counts,
                "health_score": (
                    float(health.health_score) if health and health.health_score else None
                ),
                "recommendations": len(recommendations),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
            steps=len(analyses),
        )

    async def _run_single(
        self,
        service: GrowthAnalyticsService,
        ctx: ExecutorContext,
        analysis_type: GrowthAnalysisType,
        period_start: datetime,
        period_end: datetime,
    ) -> ExecutorResult:
        analysis = await service.run_analysis(
            ctx.organization_id,
            analysis_type=analysis_type,
            period_start=period_start,
            period_end=period_end,
            generated_by="growth_agent",
        )
        return ExecutorResult(
            success=True,
            output={
                "analysis_id": str(analysis.id),
                "analysis_type": analysis_type.value,
                "status": analysis.status.value,
                "summary": analysis.summary,
                "generated_at": analysis.generated_at.isoformat(),
            },
            steps=1,
        )

    @staticmethod
    def _parse_period(raw: Any, *, default: datetime | None) -> datetime:
        if raw is None:
            return default or datetime.utcnow()
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            value = default or datetime.utcnow()
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value


register_executor(GrowthAgentExecutor())
