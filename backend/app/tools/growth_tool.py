"""Tool: growth_analysis — deterministic growth intelligence for the current org.

Runs a deterministic growth-analysis engine (KPIs, pipeline, funnel,
conversion, revenue, activity, bottlenecks, opportunities, trends, or health)
over an org-scoped snapshot and returns the structured result. The tool is
read-only: it never persists rows; the growth agent executor owns persistence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.enums import GrowthAnalysisType
from app.services.growth_analytics_service import GrowthAnalyticsService
from app.tools.base import Tool, ToolResult

_DESCRIPTION = (
    "Run a deterministic growth analysis for the current organization "
    "(kpis, pipeline, funnel, conversion, revenue, activity, bottlenecks, "
    "opportunities, trends, or health) and return the structured result. "
    "This is read-only and does not persist anything."
)

_VALID_TYPES = tuple(item.value for item in GrowthAnalysisType)


class GrowthAnalysisTool(Tool):
    """Runs an M7 deterministic growth engine for the AI brain."""

    name = "growth_analysis"
    description = _DESCRIPTION.strip()
    parameters = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": list(_VALID_TYPES),
                "description": "Which deterministic engine to run.",
            },
            "period_start": {
                "type": "string",
                "format": "date-time",
                "description": "ISO-8601 window start (defaults to 30 days ago).",
            },
            "period_end": {
                "type": "string",
                "format": "date-time",
                "description": "ISO-8601 window end (defaults to now).",
            },
        },
        "required": ["analysis_type"],
    }

    def __init__(self, session: Any, organization_id: Any) -> None:
        self._session = session
        self._organization_id = organization_id

    @classmethod
    def instantiate(cls, context: Any) -> GrowthAnalysisTool:
        from app.tools.registry import ToolContext

        if not isinstance(context, ToolContext):
            raise ImportError("GrowthAnalysisTool requires a ToolContext with a session")
        if context.session is None:
            raise ImportError("GrowthAnalysisTool requires a database session")
        return cls(context.session, context.organization_id)

    async def run(self, input: dict[str, Any]) -> ToolResult:
        raw_type = input.get("analysis_type") or "kpis"
        if raw_type not in _VALID_TYPES:
            return ToolResult(
                ok=False,
                error=(
                    f"unknown analysis_type {raw_type!r}; expected one of {', '.join(_VALID_TYPES)}"
                ),
            )

        period_end = self._parse_period(input.get("period_end"), default=None)
        period_start = self._parse_period(
            input.get("period_start"),
            default=(period_end or datetime.utcnow()) - timedelta(days=30),
        )
        period_end = period_end or datetime.utcnow()

        try:
            service = GrowthAnalyticsService(self._session)
            payload = await service.preview_analysis(
                self._organization_id,
                analysis_type=GrowthAnalysisType(raw_type),
                period_start=period_start,
                period_end=period_end,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the brain as a tool error
            return ToolResult(ok=False, error=f"growth_analysis failed: {exc}")

        return ToolResult(ok=True, content=payload)

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
