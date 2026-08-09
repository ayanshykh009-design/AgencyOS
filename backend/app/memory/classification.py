"""Memory classification: the canonical 8-type derivation and normalization.

M4 defines exactly eight canonical memory types, derived deterministically
from the stored attributes (no embeddings, no LLM classification):

- Long-term memories (``memory_type='long_term'``, ``scope='manual'``) carry a
  ``metadata_["category"]`` in ``founder | business | crm | knowledge``.
- Working memories (``memory_type='working'``) carry a ``scope`` in
  ``conversation | research | workflow | shared_context``.

These derive cleanly (all 8 are reachable), are stable (the mapping is a pure
function of stored columns), and are readable by name. They are used to
segment memory retrieval and to label provenance in ``docs/api/endpoints/memory.md``.
"""
from __future__ import annotations

import re
from enum import StrEnum

from app.models.enums import MemoryScope, MemoryType

KNOWLEDGE_CATEGORIES: frozenset[str] = frozenset(
    {"founder", "business", "crm", "knowledge"}
)


class CanonicalMemoryType(StrEnum):
    """The canonical eight memory types (see module docstring)."""

    FOUNDER = "founder"
    BUSINESS = "business"
    CRM = "crm"
    KNOWLEDGE = "knowledge"
    CONVERSATION = "conversation"
    RESEARCH = "research"
    WORKFLOW = "workflow"
    SHARED_CONTEXT = "shared_context"


_WHITESPACE = re.compile(r"\s+")


def normalize_content(content: str, max_len: int = 400) -> str:
    """Produce a canonical form of ``content`` for duplicate detection.

    Lowercases, collapses whitespace runs, strips, and truncates. This is
    stable and locale-independent; it is the only basis used for
    ``find_duplicate``, so the stored content is never mutated.
    """
    normalized = _WHITESPACE.sub(" ", content).strip().lower()
    if max_len and len(normalized) > max_len:
        normalized = normalized[:max_len]
    return normalized


def infer_scope(source: str | None) -> MemoryScope:
    """Map a free-form capture ``source`` to a working ``MemoryScope``.

    Recognized sources map to themselves; an unrecognized (or empty) source
    defaults to ``research``. Manual long-term entries set ``scope='manual'``
    explicitly and never go through this path.
    """
    if source:
        key = source.strip().lower()
        for scope in (
            MemoryScope.CONVERSATION,
            MemoryScope.RESEARCH,
            MemoryScope.WORKFLOW,
            MemoryScope.SHARED_CONTEXT,
            MemoryScope.KNOWLEDGE,
        ):
            if key == scope.value:
                return scope
    return MemoryScope.RESEARCH


def classify_canonical_type(
    memory_type: MemoryType | str,
    scope: MemoryScope | str | None = None,
    category: str | None = None,
) -> CanonicalMemoryType:
    """Derive the canonical type from stored attributes.

    Long-term memories map by their knowledge category; working memories map
    by their scope. Unknown category/scope fall back to the corresponding
    default bucket rather than raising, so legacy or malformed rows remain
    retrievable and never crash the pipeline.
    """
    resolved_type = MemoryType(memory_type)
    if resolved_type == MemoryType.LONG_TERM:
        if category and category.lower() in KNOWLEDGE_CATEGORIES:
            return CanonicalMemoryType(category.lower())
        return CanonicalMemoryType.BUSINESS
    if scope is not None:
        resolved_scope = MemoryScope(scope)
        for canonical in (
            CanonicalMemoryType.CONVERSATION,
            CanonicalMemoryType.RESEARCH,
            CanonicalMemoryType.WORKFLOW,
            CanonicalMemoryType.SHARED_CONTEXT,
        ):
            if resolved_scope.value == canonical.value:
                return canonical
    return CanonicalMemoryType.RESEARCH
