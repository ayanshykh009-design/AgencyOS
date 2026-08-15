"""Intelligence services package (M9 Founder Intelligence & Growth Triage).

- ``signal_normalizer`` — deterministic normalization of M7/M8 output into
  :class:`SignalCandidate` units (severity/confidence/impact mapping, content
  hash, bounded pipeline condition detectors).
- ``triage_scorer`` — versioned, deterministic priority scoring.
- ``founder_intelligence_service`` — read + founder-interaction surface
  (list/get/acknowledge/dismiss + roll-up summary + optional narrative).
- ``intelligence_triage_service`` — the per-org sweep (write side).
"""

from app.services.intelligence.founder_intelligence_service import FounderIntelligenceService
from app.services.intelligence.intelligence_triage_service import IntelligenceTriageService
from app.services.intelligence.signal_normalizer import (
    PIPELINE_FRESH_DAYS,
    PIPELINE_LEAD_SCAN_CAP,
    PIPELINE_STUCK_DAYS,
    PIPELINE_VALUE_THRESHOLD,
    SignalCandidate,
    SignalNormalizer,
    compute_content_hash,
)
from app.services.intelligence.triage_scorer import (
    HIGH_BAND,
    MEDIUM_BAND,
    TriageScorer,
)

__all__ = [
    "FounderIntelligenceService",
    "IntelligenceTriageService",
    "SignalCandidate",
    "SignalNormalizer",
    "TriageScorer",
    "compute_content_hash",
    "HIGH_BAND",
    "MEDIUM_BAND",
    "PIPELINE_FRESH_DAYS",
    "PIPELINE_LEAD_SCAN_CAP",
    "PIPELINE_STUCK_DAYS",
    "PIPELINE_VALUE_THRESHOLD",
]
