"""Context assembly for the AI brain.

Collects all relevant lead, research, and conversation data and formats it
into a system prompt + message history suitable for the LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.llm.models import LLMMessage, MessageRole

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.lead_research import LeadResearch


def build_system_prompt(
    *,
    lead: Lead,
    research: LeadResearch | None,
    recent_messages: list[dict[str, Any]] | None = None,
    memory_context: str | None = None,
) -> str:
    """Build the system prompt that gives the brain full context.

    ``memory_context`` (optional, pre-assembled by the memory layer) is
    appended under a ``=== MEMORY CONTEXT ===`` header; when ``None`` the
    prompt is byte-identical to the pre-M4 form.
    """
    parts: list[str] = [
        "You are an AI outreach agent for a B2B agency. Your job is to research leads, "
        "draft personalized outreach, and dispatch it via automation. You have access to "
        "tools for lead search, research, web search, HTTP fetching, draft generation, "
        "and n8n dispatch.",
        "",
        f"Current lead: {lead.first_name or ''} {lead.last_name or ''}".strip(),
        f"Company: {lead.company or 'Unknown'}",
        f"Role: {lead.position or 'Unknown'}",
        f"Location: {lead.location or 'Unknown'}",
        f"Email: {lead.email or 'N/A'}",
        f"LinkedIn: {lead.linkedin_url or 'N/A'}",
        "",
    ]

    if research and research.status == "completed":
        parts.append("=== RESEARCH CONTEXT ===")
        if research.company_overview:
            parts.append(f"Company Overview: {research.company_overview[:500]}")
        if research.pain_points:
            pp = "; ".join(str(p) for p in research.pain_points[:5])
            parts.append(f"Pain Points: {pp}")
        if research.tech_stack:
            ts = "; ".join(str(t) for t in research.tech_stack[:5])
            parts.append(f"Tech Stack: {ts}")
        if research.recent_news:
            news = "; ".join(str(n)[:200] for n in research.recent_news[:3])
            parts.append(f"Recent News: {news}")
        if research.linkedin_summary:
            parts.append(f"LinkedIn Summary: {research.linkedin_summary[:300]}")
        parts.append("")

    if recent_messages:
        parts.append("=== RECENT CONVERSATION ===")
        for msg in recent_messages[-6:]:  # last 6 messages
            role = msg.get("role", "user")
            content = msg.get("content", "")[:300]
            parts.append(f"{role.upper()}: {content}")
        parts.append("")

    if memory_context:
        parts.append("=== MEMORY CONTEXT ===")
        parts.append(memory_context)
        parts.append("")

    parts.append("=== AVAILABLE TOOLS ===")
    parts.append("Use the provided tools to gather more info, draft messages, and dispatch.")

    return "\n".join(parts)


def build_message_history(
    recent_messages: list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
) -> list[LLMMessage]:
    """Convert stored conversation messages into LLMMessage list."""
    messages: list[LLMMessage] = []
    if system_prompt:
        messages.append(LLMMessage(role=MessageRole.SYSTEM, content=system_prompt))

    if recent_messages:
        for msg in recent_messages[-10:]:  # last 10 turns
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "assistant":
                messages.append(LLMMessage(role=MessageRole.ASSISTANT, content=content))
            elif role == "tool":
                # Tool results are surfaced as user messages with a prefix
                messages.append(
                    LLMMessage(role=MessageRole.USER, content=f"[Tool Result] {content}")
                )
            else:
                messages.append(LLMMessage(role=MessageRole.USER, content=content))

    return messages
