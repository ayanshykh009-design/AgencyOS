"""KnowledgeItem model — durable long-term knowledge, org-scoped.

Knowledge items are promoted from working memories (``source_memory_id``) or
created directly. Unlike working memory they are never auto-deleted.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ai_memory import AiMemory
    from app.models.organization import Organization


class KnowledgeItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A durable knowledge entry derived from or curated for an organization."""

    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(title)) > 0", name="chk_knowledge_items_title_not_blank"
        ),
        CheckConstraint(
            "length(btrim(content)) > 0", name="chk_knowledge_items_content_not_blank"
        ),
        CheckConstraint(
            "length(btrim(category)) > 0",
            name="chk_knowledge_items_category_not_blank",
        ),
        Index("idx_knowledge_items_org_category", "organization_id", "category"),
        Index("idx_knowledge_items_org_created", "organization_id", "created_at"),
        Index("idx_knowledge_items_source_memory", "source_memory_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_memory_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_memories.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, default="general", nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}", nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="knowledge_items")
    source_memory: Mapped[AiMemory | None] = relationship(back_populates="knowledge_items")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<KnowledgeItem id={self.id} category={self.category!r} title={self.title!r}>"
