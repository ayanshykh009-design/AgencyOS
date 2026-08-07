"""WorkerHealth repository (per-instance heartbeat upserts)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker_health import WorkerHealth

if TYPE_CHECKING:
    pass


class WorkerHealthRepository:
    """Data access for worker heartbeat rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        worker_type: str,
        instance_id: uuid.UUID,
        pid: int,
        hostname: str,
        loop_ok: bool,
        last_error: str | None,
        counters: dict,
        heartbeat_at: datetime,
    ) -> None:
        """Insert or update the single heartbeat row for (type, instance)."""
        values = {
            "worker_type": worker_type,
            "instance_id": instance_id,
            "pid": pid,
            "hostname": hostname,
            "loop_ok": loop_ok,
            "last_error": last_error,
            "counters": counters,
            "last_heartbeat_at": heartbeat_at,
        }
        stmt = insert(WorkerHealth).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_worker_health_type_instance",
            set_={
                "pid": pid,
                "hostname": hostname,
                "loop_ok": loop_ok,
                "last_error": last_error,
                "counters": counters,
                "last_heartbeat_at": heartbeat_at,
            },
        )
        await self._session.execute(stmt)

    async def list_alive(
        self,
        worker_type: str | None = None,
        *,
        stale_within_seconds: int,
        limit: int = 50,
    ) -> list[WorkerHealth]:
        """List workers that have heartbeated within the staleness window."""
        cutoff = datetime.now().astimezone() - timedelta(seconds=stale_within_seconds)
        stmt = select(WorkerHealth).where(WorkerHealth.last_heartbeat_at >= cutoff)
        if worker_type is not None:
            stmt = stmt.where(WorkerHealth.worker_type == worker_type)
        stmt = stmt.order_by(WorkerHealth.worker_type, WorkerHealth.last_heartbeat_at.desc())
        stmt = stmt.limit(min(limit, 200))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_stale(
        self,
        *,
        stale_within_seconds: int,
        worker_type: str | None = None,
    ) -> int:
        cutoff = datetime.now().astimezone() - timedelta(seconds=stale_within_seconds)
        stmt = (
            select(func.count(WorkerHealth.id))
            .select_from(WorkerHealth)
            .where(WorkerHealth.last_heartbeat_at < cutoff)
        )
        if worker_type is not None:
            stmt = stmt.where(WorkerHealth.worker_type == worker_type)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def delete_stale_older_than(
        self, cutoff: datetime, batch: int
    ) -> int:
        """Prune at most ``batch`` heartbeat rows older than ``cutoff``.

        Removes heartbeats for instances that have been gone long past the
        retention window (retention sweep); bounded by ``batch``.
        """
        subq = (
            select(WorkerHealth.id)
            .where(WorkerHealth.last_heartbeat_at < cutoff)
            .order_by(WorkerHealth.last_heartbeat_at)
            .limit(max(batch, 1))
        )
        stmt = delete(WorkerHealth).where(WorkerHealth.id.in_(subq))
        result = cast(CursorResult, await self._session.execute(stmt))
        return result.rowcount or 0
