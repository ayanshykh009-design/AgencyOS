"""Task model — org-scoped to-dos linked to leads and team members.

Tasks support due/reminder scheduling and optional recurrence. Completing a
recurring task advances ``due_at``/``reminder_at`` to the next occurrence and
reopens it (single row = the task template); non-recurring tasks close out
with ``completed_at``. The ``completed_at``/status consistency is enforced
both in the schema (CHECK) and the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RecurrenceFrequency, TaskPriority, TaskStatus

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.user import User


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A to-do tracked by an organization (optionally tied to a lead)."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("length(btrim(title)) > 0", name="chk_tasks_title_not_blank"),
        CheckConstraint(
            "completed_at IS NULL OR status = 'completed'",
            name="chk_tasks_completed_at_consistent",
        ),
        CheckConstraint(
            "(recurrence_frequency IS NULL) = (recurrence_interval IS NULL)",
            name="chk_tasks_recurrence_paired",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=TaskStatus.TODO,
        nullable=False,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(
            TaskPriority,
            name="task_priority",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=TaskPriority.MEDIUM,
        nullable=False,
    )
    due_at: Mapped[datetime | None] = mapped_column()
    reminder_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    recurrence_frequency: Mapped[RecurrenceFrequency | None] = mapped_column(
        Enum(
            RecurrenceFrequency,
            name="recurrence_frequency",
            native_enum=True,
            validate_strings=True,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    recurrence_interval: Mapped[int | None] = mapped_column(Integer)

    lead: Mapped[Lead | None] = relationship(back_populates="tasks")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_user_id])

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Task id={self.id} title={self.title!r} status={self.status}>"
