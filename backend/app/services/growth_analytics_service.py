"""Growth analytics service — M7 orchestration for the deterministic growth agent.

Thin orchestration over the growth repositories. Runs the pure deterministic
engines on an org-scoped :class:`GrowthContext`, persists snapshots into
``growth_analyses`` (one row per analysis type), materializes evidence-backed
``growth_recommendations``, and owns saved ``growth_scenarios`` plus the
versioned health-weight sets. The router calls this service; it never touches
SQL or ORM sessions directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import (
    GrowthAnalysisStatus,
    GrowthAnalysisType,
    RecommendationPriority,
    RecommendationStatus,
)
from app.models.growth_analysis import GrowthAnalysis
from app.models.growth_forecast import GrowthForecast
from app.models.growth_health_weight import GrowthHealthWeight
from app.models.growth_recommendation import GrowthRecommendation
from app.models.growth_scenario import GrowthScenario
from app.repositories.growth_analysis import GrowthAnalysisRepository
from app.repositories.growth_context import GrowthContextRepository
from app.repositories.growth_forecast import GrowthForecastRepository
from app.repositories.growth_health_weight import GrowthHealthWeightRepository
from app.repositories.growth_recommendation import GrowthRecommendationRepository
from app.repositories.growth_scenario import GrowthScenarioRepository
from app.services.base import commit_with_retry
from app.services.growth_analytics.activity import compute_activity
from app.services.growth_analytics.bottleneck import compute_bottlenecks
from app.services.growth_analytics.conversion import compute_conversion
from app.services.growth_analytics.datatypes import GrowthContext
from app.services.growth_analytics.forecast import build_forecast_payload
from app.services.growth_analytics.funnel import compute_funnel
from app.services.growth_analytics.health import DEFAULT_WEIGHTS, compute_health
from app.services.growth_analytics.kpis import compute_kpi_evidence, compute_kpis
from app.services.growth_analytics.opportunity import compute_opportunities
from app.services.growth_analytics.pipeline import compute_pipeline
from app.services.growth_analytics.recommendations import generate_recommendations
from app.services.growth_analytics.revenue import compute_revenue
from app.services.growth_analytics.scenario import apply_deltas
from app.services.growth_analytics.trend import compute_trends

_ALL_TYPES = list(GrowthAnalysisType)

_ENGINE_RUNNERS: dict[GrowthAnalysisType, Any] = {
    GrowthAnalysisType.KPIS: compute_kpis,
    GrowthAnalysisType.PIPELINE: compute_pipeline,
    GrowthAnalysisType.FUNNEL: compute_funnel,
    GrowthAnalysisType.CONVERSION: compute_conversion,
    GrowthAnalysisType.REVENUE: compute_revenue,
    GrowthAnalysisType.ACTIVITY: compute_activity,
    GrowthAnalysisType.BOTTLENECKS: compute_bottlenecks,
    GrowthAnalysisType.OPPORTUNITIES: compute_opportunities,
    GrowthAnalysisType.TRENDS: compute_trends,
    GrowthAnalysisType.HEALTH: compute_health,
}

_SUMMARY_FORMATS: dict[GrowthAnalysisType, str] = {
    GrowthAnalysisType.KPIS: (
        "KPI snapshot: {totals[won_leads]} won of {totals[total_leads]} leads, "
        "weighted pipeline {pipeline_value[weighted_pipeline_value]}."
    ),
    GrowthAnalysisType.PIPELINE: (
        "Pipeline snapshot: {total_open} open deals worth {open_value} (weighted {weighted_value})."
    ),
    GrowthAnalysisType.FUNNEL: (
        "Funnel snapshot: {entry} leads entered; {exit_won} won and {exit_lost} lost."
    ),
    GrowthAnalysisType.CONVERSION: (
        "Conversion snapshot: win rate {win_rate}, overall conversion {overall_conversion}."
    ),
    GrowthAnalysisType.REVENUE: (
        "Revenue snapshot: {won_revenue_period} won this period; "
        "pipeline coverage {pipeline_coverage}."
    ),
    GrowthAnalysisType.ACTIVITY: (
        "Activity snapshot: {outreach[sent]} sent, {outreach[replied]} "
        "replies, {tasks[completed]}/{tasks[created]} tasks done."
    ),
    GrowthAnalysisType.BOTTLENECKS: (
        "Bottleneck snapshot: {primary[stage]} with {primary[dropoff]} "
        "drops ({primary[dropoff_ratio]})."
    ),
    GrowthAnalysisType.OPPORTUNITIES: (
        "Opportunity snapshot: {top_opportunities[0][name]} is the top weighted deal."
    ),
    GrowthAnalysisType.TRENDS: (
        "Trend snapshot: revenue trend {revenue[trend]}, lead trend {leads[trend]}."
    ),
    GrowthAnalysisType.HEALTH: "Growth health score is {score} out of 100.",
}


class GrowthAnalyticsService:
    """Owns the M7 growth analysis transactions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._analyses = GrowthAnalysisRepository(session)
        self._recommendations = GrowthRecommendationRepository(session)
        self._scenarios = GrowthScenarioRepository(session)
        self._health_weights = GrowthHealthWeightRepository(session)
        self._forecasts = GrowthForecastRepository(session)
        self._context = GrowthContextRepository(session)

    # -- context --------------------------------------------------------

    async def _build_context(
        self,
        organization_id: uuid.UUID,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> GrowthContext:
        if period_end < period_start:
            raise AppError(
                code="growth_analysis.period_invalid",
                message="period_end must be on or after period_start",
                status_code=422,
            )
        return await self._context.build(
            organization_id,
            period_start=period_start,
            period_end=period_end,
        )

    # -- analyses -------------------------------------------------------

    async def list_analyses(
        self,
        organization_id: uuid.UUID,
        *,
        analysis_type: GrowthAnalysisType | None = None,
        status: GrowthAnalysisStatus | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrowthAnalysis]:
        return await self._analyses.list_by_filters(
            organization_id,
            analysis_type=analysis_type,
            status=status,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )

    async def get_analysis(
        self, organization_id: uuid.UUID, analysis_id: uuid.UUID
    ) -> GrowthAnalysis:
        return await self._analyses.get_or_404(organization_id, analysis_id)

    async def preview_analysis(
        self,
        organization_id: uuid.UUID,
        *,
        analysis_type: GrowthAnalysisType,
        period_start: datetime,
        period_end: datetime,
    ) -> dict:
        """Run one deterministic engine in-memory without persisting a snapshot."""
        context = await self._build_context(
            organization_id, period_start=period_start, period_end=period_end
        )
        details, _evidence, weights = self._run_engine(analysis_type, context)
        return {"analysis_type": analysis_type.value, "details": details, "weights": weights}

    async def run_analysis(
        self,
        organization_id: uuid.UUID,
        *,
        analysis_type: GrowthAnalysisType,
        period_start: datetime,
        period_end: datetime,
        generated_by: str = "agent",
    ) -> GrowthAnalysis:
        """Run a single deterministic engine and persist its snapshot."""
        context = await self._build_context(
            organization_id, period_start=period_start, period_end=period_end
        )
        try:
            details, evidence, weights = self._run_engine(analysis_type, context)
        except Exception as exc:  # pragma: no cover - defensive
            analysis = await self._persist_analysis(
                organization_id,
                analysis_type=analysis_type,
                period_start=period_start,
                period_end=period_end,
                summary="Analysis failed",
                details={},
                evidence=[],
                weights={},
                metrics_used=self._metrics_used(context),
                generated_by=generated_by,
                status=GrowthAnalysisStatus.FAILED,
                error=str(exc),
            )
            await commit_with_retry(self._session)
            return analysis

        analysis = await self._persist_analysis(
            organization_id,
            analysis_type=analysis_type,
            period_start=period_start,
            period_end=period_end,
            summary=self._summarize(analysis_type, details),
            details=details,
            evidence=evidence,
            weights=weights,
            metrics_used=self._metrics_used(context),
            generated_by=generated_by,
        )
        await commit_with_retry(self._session)
        return analysis

    async def run_full_analysis(
        self,
        organization_id: uuid.UUID,
        *,
        period_start: datetime,
        period_end: datetime,
        generated_by: str = "agent",
    ) -> list[GrowthAnalysis]:
        """Run every deterministic engine and persist one snapshot per type."""
        context = await self._build_context(
            organization_id, period_start=period_start, period_end=period_end
        )
        results: dict[str, dict] = {}
        analyses: list[GrowthAnalysis] = []
        weights_by_type: dict[GrowthAnalysisType, dict] = {}

        for analysis_type in _ALL_TYPES:
            try:
                details, evidence, weights = self._run_engine(analysis_type, context)
            except Exception as exc:  # pragma: no cover - defensive
                analysis = await self._persist_analysis(
                    organization_id,
                    analysis_type=analysis_type,
                    period_start=period_start,
                    period_end=period_end,
                    summary="Analysis failed",
                    details={},
                    evidence=[],
                    weights={},
                    metrics_used=self._metrics_used(context),
                    generated_by=generated_by,
                    status=GrowthAnalysisStatus.FAILED,
                    error=str(exc),
                )
                analyses.append(analysis)
                continue

            results[analysis_type.value] = details
            weights_by_type[analysis_type] = weights
            analyses.append(
                await self._persist_analysis(
                    organization_id,
                    analysis_type=analysis_type,
                    period_start=period_start,
                    period_end=period_end,
                    summary=self._summarize(analysis_type, details),
                    details=details,
                    evidence=evidence,
                    weights=weights,
                    metrics_used=self._metrics_used(context),
                    generated_by=generated_by,
                )
            )

        recommendations = generate_recommendations(results)
        anchor = next(
            (
                analysis.id
                for analysis in analyses
                if analysis.analysis_type == GrowthAnalysisType.HEALTH
                and analysis.status == GrowthAnalysisStatus.COMPLETED
            ),
            None,
        )
        for item in recommendations:
            self._add_recommendation(
                organization_id,
                recommendation_type=item["type"],
                priority=item["priority"],
                status=item["status"],
                title=item["summary"],
                summary=item["description"],
                rationale=item["action"],
                action_type=item["type"],
                action_payload={"metric_target": item["metric_target"]},
                source_analysis_id=anchor,
                evidence=[{"metric_target": item["metric_target"]}],
            )

        await commit_with_retry(self._session)
        return analyses

    def _run_engine(
        self,
        analysis_type: GrowthAnalysisType,
        context: GrowthContext,
    ) -> tuple[dict, list[dict], dict]:
        """Run one engine: (details, evidence, weights)."""
        runner = _ENGINE_RUNNERS[analysis_type]
        details = runner(context)

        if analysis_type == GrowthAnalysisType.HEALTH:
            weights = self._effective_weights(context)
            details["weights"] = weights
            evidence = [
                {
                    "kpi": dimension,
                    "value": scores["score"],
                    "detail": scores["label"],
                }
                for dimension, scores in details["dimensions"].items()
            ]
            return details, evidence, weights

        if analysis_type == GrowthAnalysisType.KPIS:
            evidence = compute_kpi_evidence(context, details)
        else:
            evidence = []

        return details, evidence, {}

    # -- recommendations -------------------------------------------------

    async def list_recommendations(
        self,
        organization_id: uuid.UUID,
        *,
        status: RecommendationStatus | None = None,
        priority: RecommendationPriority | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrowthRecommendation]:
        return await self._recommendations.list_for_org(
            organization_id,
            status=status,
            priority=priority,
            limit=limit,
            offset=offset,
        )

    async def recommendation_counts(
        self, organization_id: uuid.UUID
    ) -> dict[RecommendationStatus, int]:
        return await self._recommendations.count_by_status(organization_id)

    async def update_recommendation(
        self,
        organization_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        *,
        status: RecommendationStatus | None = None,
        priority: RecommendationPriority | None = None,
    ) -> GrowthRecommendation:
        recommendation = await self._recommendations.get_or_404(organization_id, recommendation_id)
        if status is not None:
            recommendation.status = status
        if priority is not None:
            recommendation.priority = priority
        await commit_with_retry(self._session)
        return recommendation

    def _add_recommendation(
        self,
        organization_id: uuid.UUID,
        *,
        recommendation_type: str,
        priority: str,
        status: str,
        title: str,
        summary: str,
        rationale: str | None,
        action_type: str | None,
        action_payload: dict,
        source_analysis_id: uuid.UUID | None,
        evidence: list[dict],
    ) -> None:
        recommendation = GrowthRecommendation(
            organization_id=organization_id,
            recommendation_type=recommendation_type,
            priority=RecommendationPriority(priority),
            confidence=RecommendationPriority(priority),
            status=RecommendationStatus(status),
            title=title,
            summary=summary,
            rationale=rationale,
            action_type=action_type,
            action_payload=action_payload,
            source_analysis_id=source_analysis_id,
            evidence=evidence,
        )
        self._recommendations.add(recommendation)

    # -- scenarios --------------------------------------------------------

    async def list_scenarios(
        self,
        organization_id: uuid.UUID,
        *,
        forecast_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GrowthScenario]:
        return await self._scenarios.list_for_org(
            organization_id, forecast_id=forecast_id, limit=limit, offset=offset
        )

    async def get_scenario(
        self, organization_id: uuid.UUID, scenario_id: uuid.UUID
    ) -> GrowthScenario:
        return await self._scenarios.get_or_404(organization_id, scenario_id)

    async def create_scenario(
        self,
        organization_id: uuid.UUID,
        *,
        name: str,
        description: str | None,
        assumption_deltas: dict[str, Any],
        period_start: datetime,
        period_end: datetime,
        forecast_id: uuid.UUID | None = None,
        created_by_user_id: uuid.UUID | None = None,
    ) -> GrowthScenario:
        """Evaluate deltas against the live snapshot and save the projection."""
        context = await self._build_context(
            organization_id, period_start=period_start, period_end=period_end
        )
        result = apply_deltas(context, assumption_deltas)
        scenario = GrowthScenario(
            organization_id=organization_id,
            forecast_id=forecast_id,
            name=name,
            description=description,
            assumption_deltas=assumption_deltas,
            result=result,
            created_by_user_id=created_by_user_id,
        )
        self._scenarios.add(scenario)
        await commit_with_retry(self._session)
        return scenario

    async def delete_scenario(self, organization_id: uuid.UUID, scenario_id: uuid.UUID) -> None:
        if not await self._scenarios.delete(organization_id, scenario_id):
            raise AppError(
                code="growth_scenario.not_found",
                message="GrowthScenario not found",
                status_code=404,
            )
        await commit_with_retry(self._session)

    # -- health weights ----------------------------------------------------

    async def list_health_weights(
        self, organization_id: uuid.UUID, *, limit: int = 50
    ) -> list[GrowthHealthWeight]:
        return await self._health_weights.list_versions(organization_id, limit=limit)

    async def active_health_weights(self, organization_id: uuid.UUID) -> GrowthHealthWeight | None:
        return await self._health_weights.active(organization_id)

    async def upsert_health_weights(
        self,
        organization_id: uuid.UUID,
        *,
        weights: dict[str, float],
        created_by_user_id: uuid.UUID | None = None,
    ) -> GrowthHealthWeight:
        """Save a new active version, bumping the version number and
        deactivating prior versions atomically."""
        active = await self._health_weights.active(organization_id)
        version = (active.version if active else 0) + 1
        await self._health_weights.deactivate_all(organization_id)
        row = GrowthHealthWeight(
            organization_id=organization_id,
            version=version,
            weights={k: float(v) for k, v in weights.items()},
            is_active=True,
            created_by_user_id=created_by_user_id,
        )
        self._health_weights.add(row)
        await commit_with_retry(self._session)
        return row

    # -- forecast persistence ------------------------------------------------

    async def run_forecast(
        self,
        organization_id: uuid.UUID,
        *,
        method: str,
        period_start: datetime,
        period_end: datetime,
        horizon_start: datetime,
        horizon_end: datetime,
        forecast_type: str = "revenue",
    ) -> GrowthForecast:
        """Run the forecast engine and persist a ``growth_forecasts`` row."""
        context = await self._build_context(
            organization_id, period_start=period_start, period_end=period_end
        )
        payload = build_forecast_payload(context, method)
        if payload["errors"]:
            raise AppError(
                code="growth_forecast.invalid_method",
                message="; ".join(payload["errors"]),
                status_code=422,
            )
        forecast = GrowthForecast(
            organization_id=organization_id,
            forecast_type=forecast_type,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            total_value=Decimal(str(payload["point_estimate"])),
            confidence_low=Decimal(str(payload["lower_bound"])),
            confidence_high=Decimal(str(payload["upper_bound"])),
            model_config={"method": payload["method"]},
            method=payload["method"],
            base_period_start=period_start,
            base_period_end=period_end,
            point_estimate=Decimal(str(payload["point_estimate"])),
            lower_bound=Decimal(str(payload["lower_bound"])),
            upper_bound=Decimal(str(payload["upper_bound"])),
            series=payload["series"],
            errors=payload["errors"],
        )
        self._forecasts.add(forecast)
        await commit_with_retry(self._session)
        return forecast

    # -- helpers ----------------------------------------------------------

    async def _persist_analysis(
        self,
        organization_id: uuid.UUID,
        *,
        analysis_type: GrowthAnalysisType,
        period_start: datetime,
        period_end: datetime,
        summary: str,
        details: dict,
        evidence: list,
        weights: dict,
        metrics_used: list[str],
        generated_by: str,
        status: GrowthAnalysisStatus = GrowthAnalysisStatus.COMPLETED,
        error: str | None = None,
    ) -> GrowthAnalysis:
        analysis = GrowthAnalysis(
            organization_id=organization_id,
            analysis_type=analysis_type,
            status=status,
            period_start=period_start,
            period_end=period_end,
            health_score=(
                Decimal(str(details["score"]))
                if analysis_type == GrowthAnalysisType.HEALTH and details.get("score") is not None
                else None
            ),
            summary=summary,
            details=details,
            evidence=evidence,
            weights=weights,
            metrics_used=metrics_used,
            error=error,
            generated_by=generated_by,
        )
        self._analyses.add(analysis)
        return analysis

    def _summarize(self, analysis_type: GrowthAnalysisType, details: dict) -> str:
        template = _SUMMARY_FORMATS[analysis_type]
        try:
            return template.format(**details)
        except (KeyError, IndexError, ValueError, TypeError):  # pragma: no cover - defensive
            return f"{analysis_type.value} analysis completed."

    def _metrics_used(self, context: GrowthContext) -> list[str]:
        return sorted({metric.metric_type for metric in context.metrics})

    def _effective_weights(self, context: GrowthContext) -> dict[str, float]:
        """Merge built-in defaults with the org's active weight version."""
        weights: dict[str, float] = {**DEFAULT_WEIGHTS}
        for point in context.health_weights:
            weights[point.dimension] = point.weight
        return weights
