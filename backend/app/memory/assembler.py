"""Memory context assembly for the AI system prompt.

Takes the ranked memories produced by ``scoring.rank_memories`` and renders a
bounded, plain-text block that ``context_builder.build_system_prompt`` appends
under a ``=== MEMORY CONTEXT ===`` header. Budgeting is explicit:

- at most ``MAX_MEMORY_ITEMS`` (10) memories are included;
- the whole block is truncated to ``MAX_TOTAL_CHARS`` (2500) characters;
- entries are included in descending relevance (they arrive pre-ranked), so a
  tight budget only ever cuts the tail — never the most relevant context.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.memory.classification import classify_canonical_type

if TYPE_CHECKING:
    from app.models.ai_memory import AiMemory

MAX_MEMORY_ITEMS = 10
MAX_TOTAL_CHARS = 2500


def _entry_label(memory: AiMemory) -> str:
    category = None
    if memory.metadata_ and isinstance(memory.metadata_, dict):
        category = memory.metadata_.get("category")
    return classify_canonical_type(
        memory.memory_type,
        scope=memory.scope,
        category=category,
    ).value


def _render_entry(memory: AiMemory) -> str:
    title = (memory.title or memory.scope.value if memory.scope else "").strip()
    content = (memory.content or "").strip()
    header = f"[{_entry_label(memory)}]{(' ' + title) if title else ''}"
    return f"{header}\n{content}" if content else header


def assemble_memory_context(
    memories: Sequence[tuple[AiMemory, float]],
    *,
    max_items: int = MAX_MEMORY_ITEMS,
    max_chars: int = MAX_TOTAL_CHARS,
) -> str:
    """Render ranked memories into a bounded context block (or "")."""
    if not memories:
        return ""
    entries = [_render_entry(memory) for memory, _ in list(memories)[:max_items]]
    block = "\n\n".join(entries)
    if len(block) > max_chars:
        block = block[:max_chars].rstrip()
    return block
