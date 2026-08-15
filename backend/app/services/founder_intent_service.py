"""Founder intent classification — deterministic routing for the assistant.

The founder assistant never free-forms actions. Every turn is classified into a
small set of intents; the executor uses the intent to choose which tools the
brain may call and whether the reply must be grounded in retrieved context.

Classification is intentionally deterministic (keyword/structure based) so it is
testable and cannot be jailbroken into unsanctioned tool use.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FounderIntentType(StrEnum):
    """High-level category of a founder message."""

    STATUS = "status"
    ACTION = "action"
    CASUAL = "casual"
    BRAINSTORM = "brainstorm"


# Read-only tools that may answer a STATUS / BRAINSTORM turn.
_READ_TOOLS = (
    "summarize_context",
    "get_recent_activity",
    "growth_analysis",
    "lead_search",
)

# Action tooling: proposing always routes through approval.
_ACTION_TOOLS = (
    "create_task",
    "draft_email",
    "propose_founder_action",
)

_GREETING_TOKENS = {"hi", "hello", "hey", "yo", "sup", "hiya", "good morning", "good evening"}
_ACTION_KEYWORDS = (
    "create a task",
    "new task",
    "add a task",
    "send",
    "email",
    "draft",
    "outreach",
    "run the workflow",
    "run workflow",
    "export",
    "propose",
    "schedule",
    "assign",
)
_STATUS_KEYWORDS = (
    "what",
    "how many",
    "how much",
    "show",
    "report",
    "summarize",
    "status",
    "pipeline",
    "revenue",
    "leads",
    "tasks",
    "approvals",
    "proposals",
    "health",
    "kpi",
    "conversion",
    "forecast",
    "trend",
    "overview",
    "list",
)
_BRAINSTORM_KEYWORDS = (
    "idea",
    "brainstorm",
    "what if",
    "should we",
    "how could",
    "strategy",
    "plan for",
    "think about",
)


@dataclass
class FounderIntent:
    """The classified intent plus how the executor should respond."""

    intent_type: FounderIntentType
    confidence: float
    suggested_tools: list[str]
    requires_approval: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "intent_type": self.intent_type.value,
            "confidence": self.confidence,
            "suggested_tools": self.suggested_tools,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
        }


class FounderIntentService:
    """Deterministic founder-intent classifier."""

    @staticmethod
    def classify(message: str | None) -> FounderIntent:
        text = (message or "").strip().lower()
        if not text:
            return FounderIntent(
                intent_type=FounderIntentType.CASUAL,
                confidence=0.5,
                suggested_tools=list(_READ_TOOLS),
                requires_approval=False,
                reason="empty message; default to read-only context",
            )

        # Greetings only.
        if text in _GREETING_TOKENS or any(text.startswith(g) for g in _GREETING_TOKENS):
            return FounderIntent(
                intent_type=FounderIntentType.CASUAL,
                confidence=0.9,
                suggested_tools=list(_READ_TOOLS),
                requires_approval=False,
                reason="greeting detected",
            )

        # Explicit action requests always require approval routing.
        if any(kw in text for kw in _ACTION_KEYWORDS):
            return FounderIntent(
                intent_type=FounderIntentType.ACTION,
                confidence=0.85,
                suggested_tools=list(_ACTION_TOOLS),
                requires_approval=True,
                reason="action keyword detected; route through approval",
            )

        # Brainstorm / strategy.
        if any(kw in text for kw in _BRAINSTORM_KEYWORDS):
            return FounderIntent(
                intent_type=FounderIntentType.BRAINSTORM,
                confidence=0.7,
                suggested_tools=list(_READ_TOOLS),
                requires_approval=False,
                reason="brainstorm keyword detected; grounded Q&A",
            )

        # Default: a question or status request.
        if any(kw in text for kw in _STATUS_KEYWORDS):
            return FounderIntent(
                intent_type=FounderIntentType.STATUS,
                confidence=0.8,
                suggested_tools=list(_READ_TOOLS),
                requires_approval=False,
                reason="status/question keyword detected",
            )

        return FounderIntent(
            intent_type=FounderIntentType.STATUS,
            confidence=0.5,
            suggested_tools=list(_READ_TOOLS),
            requires_approval=False,
            reason="default to grounded Q&A",
        )
