"""Unit tests for M4 memory scoring and ranking (pure functions)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.memory.scoring import rank_memories, score_memory
from app.models.ai_memory import AiMemory
from app.models.enums import MemoryScope, MemoryType

NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


def _memory(
    *,
    age_days: float = 1.0,
    importance: int = 5,
    scope: MemoryScope = MemoryScope.RESEARCH,
) -> AiMemory:
    return AiMemory(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        memory_type=MemoryType.WORKING,
        scope=scope,
        content="content",
        importance=importance,
        created_at=NOW - timedelta(days=age_days),
        metadata_={},
    )


def test_recency_decays_with_age() -> None:
    fresh = score_memory(_memory(age_days=1.0), now=NOW)
    old = score_memory(_memory(age_days=25.0), now=NOW)
    assert fresh > old


def test_importance_lifts_score() -> None:
    high = score_memory(_memory(importance=5), now=NOW)
    low = score_memory(_memory(importance=1), now=NOW)
    assert high > low


def test_provenance_match_boosts_score() -> None:
    matched = score_memory(
        _memory(scope=MemoryScope.RESEARCH), metadata_={"scope": "research"}, now=NOW
    )
    mismatched = score_memory(
        _memory(scope=MemoryScope.WORKFLOW), metadata_={"scope": "research"}, now=NOW
    )
    assert matched - mismatched == pytest.approx(0.4)


def test_score_is_bounded_to_unit_interval() -> None:
    best = _memory(age_days=0.0, importance=5, scope=MemoryScope.RESEARCH)
    score = score_memory(best, metadata_={"scope": "research"}, now=NOW)
    assert 0.0 <= score <= 1.0


def test_rank_filters_below_threshold_and_orders_descending() -> None:
    high = _memory(importance=5, age_days=0.5, scope=MemoryScope.RESEARCH)
    mid = _memory(importance=3, age_days=2.0, scope=MemoryScope.RESEARCH)
    low = _memory(importance=1, age_days=29.0, scope=MemoryScope.RESEARCH)
    ranked = rank_memories([low, mid, high], metadata_={"scope": "research"}, now=NOW)
    assert [m for m, _ in ranked] == [high, mid, low]
    assert ranked[0][1] >= ranked[1][1] >= ranked[2][1]
    assert all(score >= 0.2 for _, score in ranked)


def test_rank_with_high_threshold_returns_nothing() -> None:
    ranked = rank_memories([_memory()], score_threshold=0.9, now=NOW)
    assert ranked == []


def test_rank_empty_is_empty() -> None:
    assert rank_memories([], now=NOW) == []
