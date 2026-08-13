"""AiMemory model — working + long-term memory store.

Working memories (``memory_type='working'``) are ephemeral: rows older than
``MEMORY_WORKING_TTL_DAYS`` are eligible for cleanup by the retention sweep.
Long-term memories are durable and never auto-deleted. ``source_id`` is a
polymorphic reference to the domain row a memory derives from (conversation,
lead, workflow, etc.) and carries no foreign key.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MemoryScope, MemoryType

if TYPE_CHECKING:
    from app.models.knowledge_item import KnowledgeItem
    from app.models.organization import Organization


class AiMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single AI memory row (working or long-term), org-scoped."""

    __tablename__ = "ai_memories"
    __table_args__ = (
        CheckConstraint("length(btrim(content)) > 0", name="chk_ai_memories_content_not_blank"),
        CheckConstraint(
            "title IS NULL OR length(btrim(title)) > 0",
            name="chk_ai_memories_title_not_blank",
        ),
        CheckConstraint("importance BETWEEN 1 AND 5", name="chk_ai_memories_importance_range"),
        Index("idx_ai_memories_org_type", "organization_id", "memory_type"),
        Index("idx_ai_memories_org_created", "organization_id", "created_at"),
        Index("idx_ai_memories_source_id", "source_id"),
        Index(
            "idx_ai_memories_working_ttl",
            "created_at",
            postgresql_where="memory_type = 'working'",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, name="memory_type", native_enum=True, validate_strings=True),
        default=MemoryType.WORKING,
        nullable=False,
    )
    scope: Mapped[MemoryScope] = mapped_column(
        Enum(MemoryScope, name="memory_scope", native_enum=True, validate_strings=True),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column()
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="ai_memories")
    knowledge_items: Mapped[list[KnowledgeItem]] = relationship(back_populates="source_memory")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AiMemory id={self.id} type={self.memory_type} scope={self.scope}>"
