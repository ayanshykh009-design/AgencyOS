"""Unit tests for M4 memory context assembly."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.memory.assembler import assemble_memory_context
from app.models.ai_memory import AiMemory
from app.models.enums import MemoryScope, MemoryType


def _memory(
    *,
    title: str | None,
    content: str,
    memory_type: MemoryType,
    scope: MemoryScope,
    category: str | None = None,
) -> AiMemory:
    return AiMemory(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        memory_type=memory_type,
        scope=scope,
        title=title,
        content=content,
        importance=4,
        metadata_={"category": category} if category else {},
        created_at=datetime(2026, 8, 9, tzinfo=UTC),
    )


def test_empty_input_returns_empty_string() -> None:
    assert assemble_memory_context([]) == ""


def test_renders_label_title_and_content() -> None:
    memory = _memory(
        title="Pricing concerns",
        content="Lead pushed back on annual pricing.",
        memory_type=MemoryType.WORKING,
        scope=MemoryScope.CONVERSATION,
    )
    block = assemble_memory_context([(memory, 0.9)])
    assert block == "[conversation] Pricing concerns\nLead pushed back on annual pricing."


def test_long_term_memory_labels_by_category() -> None:
    memory = _memory(
        title="Founder note",
        content="Prefers async comms.",
        memory_type=MemoryType.LONG_TERM,
        scope=MemoryScope.MANUAL,
        category="founder",
    )
    block = assemble_memory_context([(memory, 0.8)])
    assert block.startswith("[founder] Founder note\n")


def test_max_items_caps_entry_count() -> None:
    memories = [
        (
            _memory(
                title=f"t{i}",
                content=f"c{i}",
                memory_type=MemoryType.WORKING,
                scope=MemoryScope.RESEARCH,
            ),
            1.0 - i * 0.05,
        )
        for i in range(5)
    ]
    block = assemble_memory_context(memories, max_items=2)
    assert "[research] t0" in block
    assert "[research] t1" in block
    assert "[research] t2" not in block


def test_max_chars_truncates_tail_not_head() -> None:
    memories = [
        (
            _memory(
                title=f"t{i}",
                content="y" * 20,
                memory_type=MemoryType.WORKING,
                scope=MemoryScope.RESEARCH,
            ),
            1.0,
        )
        for i in range(5)
    ]
    block = assemble_memory_context(memories, max_items=5, max_chars=40)
    assert len(block) <= 40
    assert block.startswith("[research] t0")
    assert block.startswith("[research] t0")


def test_entries_without_title_label_by_scope() -> None:
    memory = _memory(
        title=None,
        content="only content here",
        memory_type=MemoryType.WORKING,
        scope=MemoryScope.WORKFLOW,
    )
    block = assemble_memory_context([(memory, 0.5)])
    assert "[workflow] workflow\nonly content here" in block
