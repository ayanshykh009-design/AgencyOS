"""Deterministic normalization of M7/M8 output into signal candidates (M9).

M9 is a triage layer: it reads source rows (growth_recommendations,
business_insights, growth_analyses snapshots, and bounded pipeline condition
detectors) and maps each into a :class:`SignalCandidate` — a normalized,
deduplicatable unit. Every mapping is deterministic:

- severity / confidence labels are mapped with fixed rules
- ``business_impact`` is extracted only from values the source actually
  carries (``amount`` is NEVER invented; it is omitted when absent)
- ``content_hash`` is a stable SHA-256 over ``(source_type, source_row_id,
  title, summary)`` so the triage worker can upsert without duplicate rows
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.models.business_insight import BusinessInsight
from app.models.enums import (
    InsightSeverity,
    InsightType,
    IntelligenceConfidence,
    IntelligenceSignalSeverity,
    RecommendationPriority,
    SignalCategory,
    SignalSourceType,
)
from app.models.growth_analysis import GrowthAnalysis
from app.models.growth_recommendation import GrowthRecommendation

# Bounded pipeline condition detectors (deterministic rules over lead rows;
# NOT metric computation — M9 never recomputes growth metrics).
PIPELINE_VALUE_THRESHOLD = 10_000.0
PIPELINE_STUCK_DAYS = 7
PIPELINE_FRESH_DAYS = 7
PIPELINE_LEAD_SCAN_CAP = 100

_PRIORITY_TO_SEVERITY = {
    RecommendationPriority.HIGH: IntelligenceSignalSeverity.HIGH,
    RecommendationPriority.MEDIUM: IntelligenceSignalSeverity.MEDIUM,
    RecommendationPriority.LOW: IntelligenceSignalSeverity.LOW,
}
_PRIORITY_TO_CONFIDENCE = {
    RecommendationPriority.HIGH: IntelligenceConfidence.HIGH,
    RecommendationPriority.MEDIUM: IntelligenceConfidence.MEDIUM,
    RecommendationPriority.LOW: IntelligenceConfidence.LOW,
}
_SEVERITY_TO_CONFIDENCE = {
    IntelligenceSignalSeverity.CRITICAL: IntelligenceConfidence.HIGH,
    IntelligenceSignalSeverity.HIGH: IntelligenceConfidence.HIGH,
    IntelligenceSignalSeverity.MEDIUM: IntelligenceConfidence.MEDIUM,
    IntelligenceSignalSeverity.LOW: IntelligenceConfidence.LOW,
    IntelligenceSignalSeverity.INFO: IntelligenceConfidence.LOW,
}


def _coerce_amount(value: Any) -> float | None:
    """Convert a numeric/string amount to float, or None when not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("$", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _extract_impact_from_evidence(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Best-effort monetary impact from evidence entries; never invents values.

    Looks for numeric keys such as ``value`` / ``amount`` / ``deal_value`` /
    ``revenue``. When none exists, returns ``{}`` (amount omitted, never zero).
    """
    for item in evidence:
        if not isinstance(item, dict):
            continue
        amount = None
        dimension: str | None = None
        for key in ("amount", "value", "deal_value", "revenue", "estimated_value"):
            candidate = item.get(key)
            if candidate is None:
                continue
            parsed = _coerce_amount(candidate)
            if parsed is not None and parsed > 0:
                amount = parsed
                dimension = str(key)
                break
        if amount is not None:
            return {"dimension": dimension, "amount": amount, "basis": "evidence"}
    return {}


def _extract_impact_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Monetary impact from a recommendation ``action_payload``.

    Honors an explicit ``impact`` block; never invents a figure.
    """
    impact = payload.get("impact") if isinstance(payload, dict) else None
    if isinstance(impact, dict):
        amount = _coerce_amount(impact.get("amount"))
        out: dict[str, Any] = {}
        dimension = impact.get("dimension")
        if dimension:
            out["dimension"] = str(dimension)
        if amount is not None:
            out["amount"] = amount
        if impact.get("basis"):
            out["basis"] = str(impact["basis"])
        if out.get("amount") is None and "dimension" not in out:
            return {}
        return out
    return {}


@dataclass(frozen=True)
class SignalCandidate:
    """One normalized, deduplicatable signal unit (before scoring)."""

    organization_id: uuid.UUID
    signal_category: SignalCategory
    source_type: SignalSourceType
    source_row_id: uuid.UUID | None
    title: str
    summary: str
    severity: IntelligenceSignalSeverity
    confidence: IntelligenceConfidence
    evidence: list[dict[str, Any]]
    business_impact: dict[str, Any]
    recommended_next_step: str | None
    urgency: float | None
    source_seen_at: datetime
    content_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_hash",
            compute_content_hash(self.source_type, self.source_row_id, self.title, self.summary),
        )


def compute_content_hash(
    source_type: SignalSourceType, source_row_id: uuid.UUID | None, title: str, summary: str
) -> str:
    """Stable dedup key over the source identity + normalized text."""
    raw = f"{source_type.value}|{source_row_id}|{title.strip()}|{summary.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SignalNormalizer:
    """Maps M7/M8 source rows to :class:`SignalCandidate` deterministically."""

    @staticmethod
    def normalize_recommendation(recommendation: GrowthRecommendation) -> SignalCandidate:
        severity = _PRIORITY_TO_SEVERITY[recommendation.priority]
        impact = _extract_impact_from_payload(recommendation.action_payload)
        if not impact:
            impact = _extract_impact_from_evidence(recommendation.evidence)
        next_step: str | None = None
        if recommendation.action_type:
            next_step = recommendation.action_type.replace("_", " ").capitalize()
        return SignalCandidate(
            organization_id=recommendation.organization_id,
            signal_category=SignalCategory.GROWTH_RECOMMENDATION,
            source_type=SignalSourceType.GROWTH_RECOMMENDATION,
            source_row_id=recommendation.id,
            title=recommendation.title,
            summary=recommendation.summary,
            severity=severity,
            confidence=_PRIORITY_TO_CONFIDENCE[recommendation.confidence],
            evidence=list(recommendation.evidence),
            business_impact=impact,
            recommended_next_step=next_step,
            urgency={RecommendationPriority.HIGH: 0.8, RecommendationPriority.MEDIUM: 0.5}.get(
                recommendation.priority, 0.3
            ),
            source_seen_at=recommendation.created_at,
        )

    @staticmethod
    def normalize_insight(insight: BusinessInsight) -> SignalCandidate:
        category = {
            InsightType.RISK: SignalCategory.PIPELINE_RISK,
            InsightType.ANOMALY: SignalCategory.GROWTH_ANOMALY,
            InsightType.OPPORTUNITY: SignalCategory.PIPELINE_OPPORTUNITY,
        }.get(insight.insight_type, SignalCategory.BUSINESS_INSIGHT)
        severity = {
            InsightSeverity.CRITICAL: IntelligenceSignalSeverity.CRITICAL,
            InsightSeverity.HIGH: IntelligenceSignalSeverity.HIGH,
            InsightSeverity.MEDIUM: IntelligenceSignalSeverity.MEDIUM,
            InsightSeverity.LOW: IntelligenceSignalSeverity.LOW,
            InsightSeverity.INFO: IntelligenceSignalSeverity.INFO,
        }[insight.severity]
        impact = _extract_impact_from_evidence(insight.metadata_.get("evidence", [])) if isinstance(
            insight.metadata_, dict
        ) else {}
        if not impact and isinstance(insight.metadata_, dict):
            impact = _extract_impact_from_payload(insight.metadata_)
        urgency = 0.8 if severity in {
            IntelligenceSignalSeverity.HIGH,
            IntelligenceSignalSeverity.CRITICAL,
        } else None
        return SignalCandidate(
            organization_id=insight.organization_id,
            signal_category=category,
            source_type=SignalSourceType.BUSINESS_INSIGHT,
            source_row_id=insight.id,
            title=insight.title,
            summary=insight.summary,
            severity=severity,
            confidence=_SEVERITY_TO_CONFIDENCE[severity],
            evidence=list(insight.metadata_.get("evidence", []))
            if isinstance(insight.metadata_, dict)
            else [],
            business_impact=impact,
            recommended_next_step=None,
            urgency=urgency,
            source_seen_at=insight.created_at,
        )

    @staticmethod
    def normalize_analysis(analysis: GrowthAnalysis) -> SignalCandidate:
        from app.models.enums import GrowthAnalysisType

        category = {
            GrowthAnalysisType.OPPORTUNITIES: SignalCategory.PIPELINE_OPPORTUNITY,
            GrowthAnalysisType.TRENDS: SignalCategory.GROWTH_ANOMALY,
            GrowthAnalysisType.BOTTLENECKS: SignalCategory.PIPELINE_RISK,
        }.get(analysis.analysis_type, SignalCategory.BUSINESS_INSIGHT)
        health = analysis.health_score
        if health is not None:
            value = float(health)
            severity = (
                IntelligenceSignalSeverity.HIGH
                if value < 50
                else IntelligenceSignalSeverity.MEDIUM
                if value < 70
                else IntelligenceSignalSeverity.LOW
            )
        else:
            severity = IntelligenceSignalSeverity.MEDIUM
        return SignalCandidate(
            organization_id=analysis.organization_id,
            signal_category=category,
            source_type=SignalSourceType.GROWTH_ANALYSIS,
            source_row_id=analysis.id,
            title=f"Growth analysis: {analysis.analysis_type.value}",
            summary=analysis.summary,
            severity=severity,
            confidence=_SEVERITY_TO_CONFIDENCE[severity],
            evidence=list(analysis.evidence),
            business_impact=_extract_impact_from_evidence(analysis.evidence),
            recommended_next_step=None,
            urgency=0.8 if severity == IntelligenceSignalSeverity.HIGH else None,
            source_seen_at=analysis.generated_at,
        )

    @staticmethod
    def normalize_pipeline_fact(lead: Any, *, rule: str) -> SignalCandidate:
        """A bounded, deterministic pipeline condition detector result.

        ``rule`` is one of ``stuck_high_value`` (risk) or
        ``fresh_high_value_proposal`` (opportunity). Reads only the lead's own
        fields — never computes metrics across rows.
        """
        value = float(lead.deal_value) if lead.deal_value is not None else 0.0
        severity = (
            IntelligenceSignalSeverity.CRITICAL
            if value >= 50_000
            else IntelligenceSignalSeverity.HIGH
            if value >= 20_000
            else IntelligenceSignalSeverity.MEDIUM
        )
        if rule == "stuck_high_value":
            category = SignalCategory.PIPELINE_RISK
            title = f"High-value deal stuck: {lead.company or lead.email or lead.id}"
            summary = (
                f"{lead.company or 'This deal'} (value ${value:,.0f}) has not moved "
                f"in {PIPELINE_STUCK_DAYS}+ days. Review next steps to avoid slippage."
            )
            urgency = 1.0
            next_step = "Review and advance this deal or update its status"
        else:
            category = SignalCategory.PIPELINE_OPPORTUNITY
            title = f"High-value proposal in flight: {lead.company or lead.email or lead.id}"
            summary = (
                f"{lead.company or 'A deal'} (value ${value:,.0f}) has a proposal sent "
                f"recently. Follow up to keep momentum."
            )
            urgency = 0.7
            next_step = "Follow up on the outstanding proposal"
        return SignalCandidate(
            organization_id=lead.organization_id,
            signal_category=category,
            source_type=SignalSourceType.PIPELINE_FACT,
            source_row_id=lead.id,
            title=title,
            summary=summary,
            severity=severity,
            confidence=IntelligenceConfidence.HIGH,
            evidence=[
                {
                    "lead_id": str(lead.id),
                    "company": lead.company,
                    "deal_value": value,
                    "status": lead.status.value if lead.status else None,
                    "rule": rule,
                }
            ],
            business_impact={"dimension": "deal_value", "amount": value, "basis": "lead"},
            recommended_next_step=next_step,
            urgency=urgency,
            source_seen_at=lead.updated_at,
        )
