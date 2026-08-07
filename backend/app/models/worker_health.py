"""WorkerHealth model — per-instance heartbeat rows for automation workers."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkerHealth(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Liveness row for one automation worker instance (upserted per loop)."""

    __tablename__ = "worker_health"
    __table_args__ = (
        CheckConstraint(
            "worker_type IN ('execution', 'credential')",
            name="chk_worker_health_type",
        ),
        UniqueConstraint(
            "worker_type", "instance_id", name="uq_worker_health_type_instance"
        ),
        Index(
            "idx_worker_health_type_heartbeat",
            "worker_type",
            "last_heartbeat_at",
        ),
        Index("idx_worker_health_heartbeat", "last_heartbeat_at"),
    )

    worker_type: Mapped[str] = mapped_column(nullable=False)
    instance_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    pid: Mapped[int] = mapped_column(nullable=False)
    hostname: Mapped[str] = mapped_column(default="", server_default="", nullable=False)
    loop_ok: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    last_error: Mapped[str | None] = mapped_column()
    counters: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WorkerHealth type={self.worker_type} instance={self.instance_id}>"
