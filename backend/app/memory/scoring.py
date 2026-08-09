"""Deterministic memory scoring for retrieval ranking.

Pure-function ranking only — no embeddings, vectors, or LLM involvement. The
score is a weighted blend of recency, importance, and provenance, each
bounded to keep the total in ``[0, 1]``:

- recency: linear decay from ``1.0`` at now to ``0.0`` at 30 days old (×0.4)
- importance: ``importance / 5`` on the stored 1–5 scale (×0.3)
- provenance: ``+0.2`` when the memory's scope matches the query context,
  ``-0.2`` on a clear mismatch, else neutral (×0.3 weighting cap)

``rank_memories`` returns the candidates at or above ``score_threshold``,
sorted by descending score. Callers bound the candidate pool first
(``AiMemoryRepository.list_ranked``) so the sort stays cheap.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.models.ai_memory import AiMemory

RECENCY_HALF_LIFE_DAYS = 30.0
IMPORTANCE_SCALE = 5.0
RECENCY_WEIGHT = 0.4
IMPORTANCE_WEIGHT = 0.3
PROVENANCE_MATCH_BONUS = 0.2
PROVENANCE_MISMATCH_PENALTY = -0.2


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _recency_score(memory: AiMemory, now: datetime) -> float:
    age = (_as_utc(now) - _as_utc(memory.created_at)).total_seconds()
    age_days = max(0.0, age / 86_400.0)
    decay = max(0.0, 1.0 - age_days / RECENCY_HALF_LIFE_DAYS)
    return decay * RECENCY_WEIGHT


def _importance_score(memory: AiMemory) -> float:
    importance = max(1, min(int(memory.importance or 1), int(IMPORTANCE_SCALE)))
    return (importance / IMPORTANCE_SCALE) * IMPORTANCE_WEIGHT


def _provenance_score(memory: AiMemory, metadata_: dict | None) -> float:
    query_scope = (metadata_ or {}).get("scope")
    if not query_scope:
        return 0.0
    memory_scope = memory.scope.value if memory.scope is not None else ""
    if memory_scope and memory_scope == str(query_scope).lower():
        return PROVENANCE_MATCH_BONUS
    if memory_scope:
        return PROVENANCE_MISMATCH_PENALTY
    return 0.0


def score_memory(
    memory: AiMemory,
    metadata_: dict | None = None,
    *,
    now: datetime | None = None,
) -> float:
    """Compute the blended score for a single memory."""
    reference = now or datetime.now(UTC)
    total = (
        _recency_score(memory, reference)
        + _importance_score(memory)
        + _provenance_score(memory, metadata_)
    )
    return max(0.0, min(1.0, total))


def rank_memories(
    memories: Sequence[AiMemory],
    metadata_: dict | None = None,
    *,
    score_threshold: float = 0.2,
    now: datetime | None = None,
) -> list[tuple[AiMemory, float]]:
    """Rank ``memories`` by blended score, descending, thresholded.

    Returns ``(memory, score)`` pairs with ``score >= score_threshold``.
    Ties break by newest ``created_at`` first for deterministic output.
    """
    reference = now or datetime.now(UTC)
    ranked: list[tuple[AiMemory, float]] = []
    for memory in memories:
        score = score_memory(memory, metadata_, now=reference)
        if score >= score_threshold:
            ranked.append((memory, score))
    ranked.sort(key=lambda pair: (-pair[1], -_created_ts(pair[0])))
    return ranked


def _created_ts(memory: AiMemory) -> float:
    return _as_utc(memory.created_at).timestamp()


def recent_age(created_at: datetime, now: datetime | None = None) -> timedelta:
    """Age of a memory at ``now`` (helper for lifecycle windows)."""
    reference = now or datetime.now(UTC)
    return _as_utc(reference) - _as_utc(created_at)
