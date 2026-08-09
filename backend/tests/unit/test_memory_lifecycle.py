"""Unit tests for M4 working-memory lifecycle (TTL + dedup)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.memory.lifecycle import is_duplicate, is_expired, working_ttl_cutoff
from app.models.ai_memory import AiMemory
from app.models.enums import MemoryScope, MemoryType

NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


def _memory(memory_type: MemoryType, age_days: float) -> AiMemory:
    return AiMemory(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        memory_type=memory_type,
        scope=MemoryScope.RESEARCH,
        content="content",
        importance=3,
        created_at=NOW - timedelta(days=age_days),
        metadata_={},
    )


def test_cutoff_is_now_minus_ttl() -> None:
    cutoff = working_ttl_cutoff(ttl_days=30, now=NOW)
    assert cutoff == NOW - timedelta(days=30)


def test_working_older_than_ttl_is_expired() -> None:
    assert is_expired(_memory(MemoryType.WORKING, 31), ttl_days=30, now=NOW)


def test_working_within_ttl_is_not_expired() -> None:
    assert not is_expired(_memory(MemoryType.WORKING, 10), ttl_days=30, now=NOW)


def test_long_term_never_expired_even_if_old() -> None:
    assert not is_expired(_memory(MemoryType.LONG_TERM, 400), ttl_days=30, now=NOW)


def test_naive_datetime_treated_as_utc() -> None:
    naive = NOW.replace(tzinfo=None) - timedelta(days=400)
    memory = _memory(MemoryType.WORKING, 0)
    memory.created_at = naive
    assert is_expired(memory, ttl_days=30, now=NOW)


def test_duplicate_detection_ignores_formatting() -> None:
    assert is_duplicate("  Follow   Up   Tomorrow  ", "follow up tomorrow")


def test_duplicate_detection_distinguishes_content() -> None:
    assert not is_duplicate("follow up tomorrow", "follow up next week")
