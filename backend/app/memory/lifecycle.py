"""Working-memory lifecycle rules: TTL expiry and write-time dedup.

Only ``memory_type='working'`` rows are ever considered expired. Long-term
memory is durable by construction and ``is_expired`` always returns ``False``
for it, so the cleanup worker can never prune durable knowledge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.memory.classification import normalize_content
from app.models.enums import MemoryType

if TYPE_CHECKING:
    from app.models.ai_memory import AiMemory


def working_ttl_cutoff(
    *,
    ttl_days: int,
    now: datetime | None = None,
) -> datetime:
    """Cutoff timestamp: rows created before this are expired working memory."""
    reference = now or datetime.now(UTC)
    return reference - timedelta(days=max(ttl_days, 1))


def is_expired(
    memory: AiMemory,
    *,
    ttl_days: int,
    now: datetime | None = None,
) -> bool:
    """True only for working memories older than the TTL window."""
    if memory.memory_type != MemoryType.WORKING:
        return False
    cutoff = working_ttl_cutoff(ttl_days=ttl_days, now=now)
    created = memory.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    else:
        created = created.astimezone(UTC)
    return created < cutoff


def is_duplicate(content_a: str, content_b: str) -> bool:
    """True when two contents are identical in canonical normalized form."""
    return normalize_content(content_a) == normalize_content(content_b)
