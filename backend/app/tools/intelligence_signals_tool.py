"""Tool: intelligence_signals — read-only founder intelligence feed for the AI brain.

Surfaces prioritized, validated business signals for the current organization
via :class:`FounderIntelligenceService`. Strictly read-only: it never persists,
mutates, or acknowledges any row. Designed for the M11 AI run surface so the
brain can reason over founder intelligence without a side-effecting tool.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.enums import (
    IntelligenceSignalStatus,
    SignalCategory,
    SignalSourceType,
)
from app.services.intelligence.founder_intelligence_service import (
    FounderIntelligenceService,
)
from app.tools.base import Tool, ToolResult

_DESCRIPTION = (
    "List founder-facing intelligence signals for the current organization "
    "(prioritized business insights derived from validated data). Read-only: "
    "this tool never mutates any row. Use filters to narrow by status, "
    "category, or source type."
)

_VALID_STATUS = tuple(item.value for item in IntelligenceSignalStatus)
_VALID_CATEGORY = tuple(item.value for item in SignalCategory)
_VALID_SOURCE = tuple(item.value for item in SignalSourceType)


class IntelligenceSignalsTool(Tool):
    """Read-only M9 intelligence feed for the AI brain (M11)."""

    name = "intelligence_signals"
    description = _DESCRIPTION.strip()
    parameters = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": list(_VALID_STATUS),
                "description": "Filter by signal status.",
            },
            "category": {
                "type": "string",
                "enum": list(_VALID_CATEGORY),
                "description": "Filter by signal category.",
            },
            "source_type": {
                "type": "string",
                "enum": list(_VALID_SOURCE),
                "description": "Filter by originating data source type.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": [],
    }

    def __init__(self, session: Any, organization_id: Any) -> None:
        self._session = session
        self._organization_id = organization_id

    @classmethod
    def instantiate(cls, context: Any) -> IntelligenceSignalsTool:
        from app.tools.registry import ToolContext

        if not isinstance(context, ToolContext):
            raise ImportError("IntelligenceSignalsTool requires a ToolContext")
        if context.session is None:
            raise ImportError("IntelligenceSignalsTool requires a database session")
        return cls(context.session, context.organization_id)

    async def run(self, input: dict[str, Any]) -> ToolResult:
        if self._session is None or self._organization_id is None:
            return ToolResult(ok=False, error="intelligence_signals tool is not configured")

        status = self._coerce_enum(
            input.get("status"), _VALID_STATUS, IntelligenceSignalStatus, "status"
        )
        if isinstance(status, ToolResult):
            return status
        category = self._coerce_enum(
            input.get("category"), _VALID_CATEGORY, SignalCategory, "category"
        )
        if isinstance(category, ToolResult):
            return category
        source_type = self._coerce_enum(
            input.get("source_type"), _VALID_SOURCE, SignalSourceType, "source_type"
        )
        if isinstance(source_type, ToolResult):
            return source_type

        try:
            limit = int(input.get("limit", 20))
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(100, limit))
        try:
            offset = int(input.get("offset", 0))
        except (TypeError, ValueError):
            offset = 0
        offset = max(0, offset)

        service = FounderIntelligenceService(self._session)
        signals = await service.list_signals(
            self._organization_id,
            status=status,
            category=category,
            source_type=source_type,
            limit=limit,
            offset=offset,
        )
        return ToolResult(ok=True, content=[self._serialize(s) for s in signals])

    @staticmethod
    def _coerce_enum(
        raw: Any,
        valid: tuple[str, ...],
        enum_cls: Any,
        field: str,
    ) -> Any:
        if raw is None or raw == "":
            return None
        if raw not in valid:
            return ToolResult(
                ok=False,
                error=f"invalid {field} {raw!r}; expected one of {', '.join(valid)}",
            )
        return enum_cls(raw)

    @staticmethod
    def _serialize(signal: Any) -> dict[str, Any]:
        def _iso(value: datetime | None) -> str | None:
            return value.isoformat() if value else None

        return {
            "id": str(signal.id),
            "signal_category": signal.signal_category.value,
            "source_type": signal.source_type.value,
            "source_row_id": str(signal.source_row_id) if signal.source_row_id else None,
            "title": signal.title,
            "summary": signal.summary,
            "severity": signal.severity.value,
            "business_impact": signal.business_impact,
            "priority_score": float(signal.priority_score),
            "priority_components": signal.priority_components,
            "evidence": signal.evidence,
            "recommended_next_step": signal.recommended_next_step,
            "confidence": signal.confidence.value,
            "status": signal.status.value,
            "content_hash": signal.content_hash,
            "first_seen_at": _iso(signal.first_seen_at),
            "last_triaged_at": _iso(signal.last_triaged_at),
            "created_at": _iso(signal.created_at),
            "updated_at": _iso(signal.updated_at),
        }
