"""Service-layer helpers shared across domains.

Services orchestrate repositories and own the transaction boundary. This
module provides the small plumbing they all share: a commit helper with
retry-on-serialization/deadlock, and a UTC clock.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import OperationalError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

logger = logging.getLogger("agencyos")


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


@retry(
    retry=retry_if_exception_type(OperationalError),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=0.1, max=2),
    reraise=True,
)
async def commit_with_retry(session) -> None:
    """Commit a session, retrying transient Postgres failures.

    Serialization/deadlock failures surface as OperationalError; the retry
    re-runs the whole transaction (new statement), so callers must build the
    transaction idempotently — see service docs.
    """
    await session.commit()
