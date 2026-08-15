"""Deterministic triage scoring for intelligence signals (M9).

``priority_score`` is a weighted sum over six bounded components
(severity, business_impact, urgency, confidence, actionability,
persistence) using fixed weights and the component→score mappings below.
The result is a number in ``[0, 1]`` and never a probability.

Missing inputs (no monetary impact, unknown urgency) fall back to a neutral
``0.5`` and are recorded under ``missing`` so callers can reason about data
quality. Everything is versioned via ``TriageScorer.VERSION`` and stored in
``priority_components`` for auditability.

Bands: ``high >= 0.7``, ``medium >= 0.45``, else ``low``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.enums import IntelligenceConfidence, IntelligenceSignalSeverity
from app.services.intelligence.signal_normalizer import SignalCandidate

HIGH_BAND = 0.7
MEDIUM_BAND = 0.45
NEUTRAL = 0.5
_PERSISTENCE_WINDOW_DAYS = 30
_IMPACT_AMOUNT_HIGH = 25_000.0

SEVERITY_SCORES = {
    IntelligenceSignalSeverity.INFO: 0.2,
    IntelligenceSignalSeverity.LOW: 0.4,
    IntelligenceSignalSeverity.MEDIUM: 0.6,
    IntelligenceSignalSeverity.HIGH: 0.8,
    IntelligenceSignalSeverity.CRITICAL: 1.0,
}
CONFIDENCE_SCORES = {
    IntelligenceConfidence.LOW: 0.35,
    IntelligenceConfidence.MEDIUM: 0.6,
    IntelligenceConfidence.HIGH: 0.85,
}


class TriageScorer:
    """Versioned, deterministic priority scorer for signal candidates."""

    VERSION = 1
    WEIGHTS: dict[str, float] = {
        "severity": 0.30,
        "business_impact": 0.25,
        "urgency": 0.15,
        "confidence": 0.10,
        "actionability": 0.10,
        "persistence": 0.10,
    }

    def score(self, candidate: SignalCandidate, *, now: datetime) -> tuple[float, dict[str, Any]]:
        """Return ``(priority_score, priority_components)``.

        ``priority_components`` is ``{"version", "components", "missing"}`` and
        is stored verbatim so the score is fully auditable.
        """
        components: dict[str, float] = {}
        missing: list[str] = []

        # severity — always known
        components["severity"] = SEVERITY_SCORES[candidate.severity]

        # business_impact — only meaningful when the source carried a figure
        impact = candidate.business_impact or {}
        amount = impact.get("amount")
        if amount is not None:
            components["business_impact"] = (
                0.8 if float(amount) >= _IMPACT_AMOUNT_HIGH else 0.6
            )
        elif impact.get("dimension"):
            components["business_impact"] = 0.5
        else:
            missing.append("business_impact")
            components["business_impact"] = NEUTRAL

        # urgency — deterministic hint from the normalizer; unknown → neutral
        if candidate.urgency is not None:
            components["urgency"] = min(1.0, max(0.0, candidate.urgency))
        else:
            missing.append("urgency")
            components["urgency"] = NEUTRAL

        # confidence — always known (defaults low)
        components["confidence"] = CONFIDENCE_SCORES[candidate.confidence]

        # actionability — a concrete next step makes the signal actionable
        components["actionability"] = 0.8 if candidate.recommended_next_step else 0.4

        # persistence — how long the underlying situation has persisted
        age_days = max(0, (now - candidate.source_seen_at).total_seconds() / 86400)
        components["persistence"] = min(1.0, age_days / _PERSISTENCE_WINDOW_DAYS)

        score = sum(weight * components[key] for key, weight in self.WEIGHTS.items())
        score = round(min(1.0, max(0.0, score)), 4)

        return score, {
            "version": self.VERSION,
            "components": {k: round(v, 4) for k, v in components.items()},
            "missing": missing,
        }

    @staticmethod
    def band(score: float) -> str:
        """Priority band label for a score (high / medium / low)."""
        if score >= HIGH_BAND:
            return "high"
        if score >= MEDIUM_BAND:
            return "medium"
        return "low"
