"""FounderIntelligenceService — read/triage surface for M9 signals.

This service is the read + founder-interaction half of M9 (list/get/acknowledge/
dismiss + roll-up summary). The write half (sweep) lives in
:class:`IntelligenceTriageService`. Both share the same repository.

Rule: the API can only acknowledge or dismiss a signal. Everything else about
a signal is written by the triage worker, and the API never mutates the M7/M8
source rows a signal points at.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.models.enums import (
    IntelligenceSignalStatus,
    SignalCategory,
    SignalSourceType,
)
from app.models.intelligence_signal import IntelligenceSignal
from app.repositories.intelligence_signal import IntelligenceSignalRepository
from app.services.base import utcnow

_TERMINAL_USER_TRANSITIONS = frozenset(
    {IntelligenceSignalStatus.ACKNOWLEDGED, IntelligenceSignalStatus.DISMISSED}
)

_NARRATIVE_PROMPT_NAME = "intelligence-narrative"
_NARRATIVE_PROMPT_VERSION = "1.0.0"
_NARRATIVE_MAX_TOKENS = 600
_NARRATIVE_TEMPERATURE = 0.2


class FounderIntelligenceService:
    """Read + founder-interaction surface for intelligence signals (M9)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IntelligenceSignalRepository(session)

    async def list_signals(
        self,
        organization_id: uuid.UUID,
        *,
        status: IntelligenceSignalStatus | None = None,
        category: SignalCategory | None = None,
        source_type: SignalSourceType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IntelligenceSignal]:
        return await self._repo.list_for_org(
            organization_id,
            status=status,
            category=category,
            source_type=source_type,
            limit=limit,
            offset=offset,
        )

    async def get_signal(
        self, organization_id: uuid.UUID, signal_id: uuid.UUID
    ) -> IntelligenceSignal:
        signal = await self._repo.get(organization_id, signal_id)
        if signal is None:
            raise AppError(
                code="intelligence_signal.not_found",
                message="Intelligence signal not found",
                status_code=404,
            )
        return signal

    async def summarize(self, organization_id: uuid.UUID) -> dict[str, Any]:
        """Roll-up counts for the founder intelligence surface."""
        statuses = await self._repo.count_by_status(organization_id)
        high, medium, low = await self._repo.priority_band_counts(
            organization_id, status=IntelligenceSignalStatus.ACTIVE
        )
        highest = await self._repo.highest_priority_score(
            organization_id, status=IntelligenceSignalStatus.ACTIVE
        )
        return {
            "active": statuses[IntelligenceSignalStatus.ACTIVE],
            "acknowledged": statuses[IntelligenceSignalStatus.ACKNOWLEDGED],
            "dismissed": statuses[IntelligenceSignalStatus.DISMISSED],
            "superseded": statuses[IntelligenceSignalStatus.SUPERSEDED],
            "high_priority": high,
            "medium_priority": medium,
            "low_priority": low,
            "highest_priority_score": highest,
        }

    async def update_status(
        self,
        organization_id: uuid.UUID,
        signal_id: uuid.UUID,
        status: IntelligenceSignalStatus,
        *,
        actor_user_id: uuid.UUID,
    ) -> IntelligenceSignal:
        """Acknowledge or dismiss a signal (idempotent; terminal-safe).

        Superseded signals are terminal and cannot be revived (409). Only
        ``acknowledged`` / ``dismissed`` are acceptable targets (422).
        """
        if status not in _TERMINAL_USER_TRANSITIONS:
            raise AppError(
                code="intelligence_signal.invalid_transition",
                message="Signals can only be acknowledged or dismissed",
                status_code=422,
            )
        current = await self._repo.get(organization_id, signal_id)
        if current is None:
            raise AppError(
                code="intelligence_signal.not_found",
                message="Intelligence signal not found",
                status_code=404,
            )
        if current.status == IntelligenceSignalStatus.SUPERSEDED:
            raise AppError(
                code="intelligence_signal.superseded",
                message="Superseded signals cannot be acknowledged or dismissed",
                status_code=409,
            )
        if current.status == status:
            return current

        updated = await self._repo.set_status(
            organization_id,
            signal_id,
            status,
            acknowledged_by_user_id=actor_user_id,
            acknowledged_at=utcnow(),
        )
        await self._session.flush()
        return updated or current

    async def generate_narrative(
        self, organization_id: uuid.UUID, signals: list[IntelligenceSignal]
    ) -> str:
        """A founder narrative over the top signals.

        Gated by ``INTELLIGENCE_NARRATIVE_ENABLED``; when the flag is off or
        the LLM fails, a deterministic summary built only from signal fields is
        returned. The prompt is a versioned library prompt and the context is
        hard-bounded, so the narrative can never exceed the configured budget.
        """
        fallback = self._deterministic_narrative(signals)
        if not settings.INTELLIGENCE_NARRATIVE_ENABLED or not signals:
            return fallback

        context = self._build_context(signals)
        if not context:
            return fallback

        try:
            llm = await self._llm_service(organization_id)
            rendered = llm.render_prompt(
                _NARRATIVE_PROMPT_NAME, _NARRATIVE_PROMPT_VERSION, {"signalsJson": context}
            )
            result = await llm.chat(
                [{"role": "system", "content": rendered}],
                max_tokens=_NARRATIVE_MAX_TOKENS,
                temperature=_NARRATIVE_TEMPERATURE,
            )
            text = getattr(result, "text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()
            return fallback
        except Exception:  # noqa: BLE001 - narrative must never break the sweep
            return fallback

    async def _llm_service(self, organization_id: uuid.UUID):
        from app.llm.service import LLMService

        return LLMService.for_provider(
            settings.LLM_PROVIDER,
            organization_id=organization_id,
            session=self._session,
            feature="intelligence.narrative",
        )

    def _build_context(self, signals: list[IntelligenceSignal]) -> str:
        """Bounded JSON context (top-N signals, deterministic fields only)."""
        import json

        top = signals[: settings.INTELLIGENCE_NARRATIVE_TOP_N]
        rows = []
        budget = settings.INTELLIGENCE_NARRATIVE_MAX_CONTEXT_CHARS
        for signal in top:
            row = {
                "title": signal.title,
                "summary": signal.summary,
                "severity": signal.severity.value,
                "businessImpact": signal.business_impact,
                "priorityScore": float(signal.priority_score),
                "confidence": signal.confidence.value,
                "evidence": signal.evidence[:5],
            }
            serialized = json.dumps(row, ensure_ascii=False)
            budget -= len(serialized)
            if budget < 0:
                break
            rows.append(serialized)
        return "[" + ",".join(rows) + "]"

    @staticmethod
    def _deterministic_narrative(signals: list[IntelligenceSignal]) -> str:
        if not signals:
            return "No significant signals today."
        top = signals[0]
        impact = top.business_impact or {}
        amount = impact.get("amount")
        if amount is not None:
            headline = (
                f"{top.title}: {top.summary} Estimated impact ${float(amount):,.0f} "
                f"(severity {top.severity.value}, confidence {top.confidence.value})."
            )
        else:
            headline = (
                f"{top.title}: {top.summary} "
                f"(severity {top.severity.value}, confidence {top.confidence.value})."
            )
        remaining = len(signals) - 1
        if remaining > 0:
            headline += f" {remaining} more signal(s) are in the active queue."
        return headline
