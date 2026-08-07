"""Worker liveness: heartbeat upserts, staleness queries, and pruning.

Thin orchestration over :class:`WorkerHealthRepository` so workers and the
monitoring endpoints share one place that owns heartbeat semantics (staleness
window, metadata assembly) while the repository owns the SQL.
"""
from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker_health import WorkerHealth
from app.repositories.worker_health import WorkerHealthRepository


class WorkerHealthService:
    """Heartbeat + liveness data access for automation worker instances."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = WorkerHealthRepository(session)

    async def heartbeat(
        self,
        *,
        worker_type: str,
        instance_id: uuid.UUID,
        loop_ok: bool,
        last_error: str | None,
        counters: dict | None = None,
        heartbeat_at: datetime | None = None,
    ) -> None:
        """Upsert this instance's heartbeat row."""
        await self._repo.upsert(
            worker_type=worker_type,
            instance_id=instance_id,
            pid=os.getpid(),
            hostname=socket.gethostname(),
            loop_ok=loop_ok,
            last_error=last_error,
            counters=counters or {},
            heartbeat_at=heartbeat_at or datetime.now().astimezone(),
        )

    async def list_alive(
        self,
        worker_type: str | None = None,
        *,
        stale_within_seconds: int,
        limit: int = 50,
    ) -> list[WorkerHealth]:
        """List worker instances that heartbeated within the staleness window."""
        return await self._repo.list_alive(
            worker_type,
            stale_within_seconds=stale_within_seconds,
            limit=limit,
        )

    async def count_stale(
        self,
        *,
        stale_within_seconds: int,
        worker_type: str | None = None,
    ) -> int:
        """Count worker instances whose heartbeat is older than the window."""
        return await self._repo.count_stale(
            stale_within_seconds=stale_within_seconds,
            worker_type=worker_type,
        )

    async def prune_dead(self, cutoff: datetime, batch: int) -> int:
        """Delete heartbeat rows not seen since ``cutoff`` (retention)."""
        return await self._repo.delete_stale_older_than(cutoff, batch)
