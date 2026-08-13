"""Outreach service: message templates, attempts, follow-ups, manual queue."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OutreachChannel, OutreachStatus
from app.models.follow_up import FollowUp
from app.models.manual_outreach_queue import ManualOutreachQueue
from app.models.outreach_attempt import OutreachAttempt
from app.models.outreach_message import OutreachMessage
from app.repositories.outreach import (
    FollowUpRepository,
    ManualOutreachQueueRepository,
    OutreachAttemptRepository,
    OutreachMessageRepository,
)
from app.services.base import commit_with_retry


class OutreachService:
    """Owns outreach rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._messages = OutreachMessageRepository(session)
        self._attempts = OutreachAttemptRepository(session)
        self._follow_ups = FollowUpRepository(session)
        self._manual = ManualOutreachQueueRepository(session)

    # -- message templates ----------------------------------------------

    async def list_messages(
        self,
        organization_id: uuid.UUID,
        *,
        channel: OutreachChannel | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OutreachMessage]:
        return await self._messages.list(
            organization_id, channel=channel, limit=limit, offset=offset
        )

    async def get_message(
        self, organization_id: uuid.UUID, message_id: uuid.UUID
    ) -> OutreachMessage:
        return await self._messages.get_or_404(organization_id, message_id)

    async def create_message(
        self, organization_id: uuid.UUID, data: dict[str, Any]
    ) -> OutreachMessage:
        message = OutreachMessage(
            organization_id=organization_id,
            name=data["name"],
            channel=OutreachChannel(data["channel"]),
            subject=data.get("subject"),
            body=data["body"],
            variables=data.get("variables", []),
            version=data.get("version", 1),
            is_active=bool(data.get("is_active", True)),
        )
        self._messages.add(message)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            await self._messages.handle_integrity_error(exc)
        await commit_with_retry(self._session)
        return message

    async def update_message(
        self,
        organization_id: uuid.UUID,
        message_id: uuid.UUID,
        data: dict[str, Any],
    ) -> OutreachMessage:
        message = await self._messages.get_or_404(organization_id, message_id)
        for field in ("name", "channel", "subject", "body", "variables", "version", "is_active"):
            if field in data:
                setattr(message, field, data[field])
        try:
            await commit_with_retry(self._session)
        except IntegrityError as exc:
            await self._session.rollback()
            await self._messages.handle_integrity_error(exc)
        return message

    async def delete_message(self, organization_id: uuid.UUID, message_id: uuid.UUID) -> None:
        message = await self._messages.get_or_404(organization_id, message_id)
        await self._session.delete(message)
        await commit_with_retry(self._session)

    # -- attempts -------------------------------------------------------

    async def list_attempts_for_lead(
        self, organization_id: uuid.UUID, lead_id: uuid.UUID
    ) -> list[OutreachAttempt]:
        return await self._attempts.list_for_lead(organization_id, lead_id)

    async def get_attempt(
        self, organization_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> OutreachAttempt:
        return await self._attempts.get_or_404(organization_id, attempt_id)

    async def create_attempt(
        self, organization_id: uuid.UUID, data: dict[str, Any]
    ) -> OutreachAttempt:
        attempt = OutreachAttempt(
            organization_id=organization_id,
            lead_id=data["lead_id"],
            outreach_message_id=data.get("outreach_message_id"),
            channel=OutreachChannel(data["channel"]),
            status=OutreachStatus(data.get("status", "queued")),
            subject=data.get("subject"),
            body=data.get("body"),
            scheduled_at=data.get("scheduled_at"),
            metadata=data.get("metadata", {}),
        )
        self._attempts.add(attempt)
        await commit_with_retry(self._session)
        return attempt

    async def update_attempt(
        self,
        organization_id: uuid.UUID,
        attempt_id: uuid.UUID,
        data: dict[str, Any],
    ) -> OutreachAttempt:
        attempt = await self._attempts.get_or_404(organization_id, attempt_id)
        for field in (
            "status",
            "scheduled_at",
            "sent_at",
            "delivered_at",
            "external_id",
            "error_code",
            "error_message",
            "metadata",
        ):
            if field in data:
                setattr(attempt, field, data[field])
        await commit_with_retry(self._session)
        return attempt

    # -- follow-ups -----------------------------------------------------

    async def list_follow_ups_for_lead(
        self, organization_id: uuid.UUID, lead_id: uuid.UUID
    ) -> list[FollowUp]:
        return await self._follow_ups.list_for_lead(organization_id, lead_id)

    async def create_follow_up(self, organization_id: uuid.UUID, data: dict[str, Any]) -> FollowUp:
        follow_up = FollowUp(
            organization_id=organization_id,
            lead_id=data["lead_id"],
            outreach_attempt_id=data.get("outreach_attempt_id"),
            channel=OutreachChannel(data["channel"]),
            sequence_position=data["sequence_position"],
            subject=data.get("subject"),
            body=data["body"],
            delay_days=data.get("delay_days", 0),
            scheduled_at=data.get("scheduled_at"),
            status=OutreachStatus(data.get("status", "queued")),
        )
        self._follow_ups.add(follow_up)
        await commit_with_retry(self._session)
        return follow_up

    async def update_follow_up(
        self,
        organization_id: uuid.UUID,
        follow_up_id: uuid.UUID,
        data: dict[str, Any],
    ) -> FollowUp:
        follow_up = await self._follow_ups.get_or_404(organization_id, follow_up_id)
        for field in ("subject", "body", "delay_days", "scheduled_at", "status", "sent_at"):
            if field in data:
                setattr(follow_up, field, data[field])
        await commit_with_retry(self._session)
        return follow_up

    # -- manual queue ---------------------------------------------------

    async def list_manual_tasks(
        self,
        organization_id: uuid.UUID,
        *,
        status: OutreachStatus | None = None,
        assigned_user_id: uuid.UUID | None = None,
    ) -> list[ManualOutreachQueue]:
        return await self._manual.list(
            organization_id,
            status=status,
            assigned_user_id=assigned_user_id,
        )

    async def get_manual_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> ManualOutreachQueue:
        return await self._manual.get_or_404(organization_id, task_id)

    async def create_manual_task(
        self, organization_id: uuid.UUID, data: dict[str, Any]
    ) -> ManualOutreachQueue:
        task = ManualOutreachQueue(
            organization_id=organization_id,
            lead_id=data["lead_id"],
            assigned_user_id=data.get("assigned_user_id"),
            channel=OutreachChannel(data["channel"]),
            status=OutreachStatus(data.get("status", "queued")),
            priority=data.get("priority", 0),
            due_at=data.get("due_at"),
            subject=data.get("subject"),
            body=data.get("body"),
            notes=data.get("notes"),
        )
        self._manual.add(task)
        await commit_with_retry(self._session)
        return task

    async def update_manual_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        data: dict[str, Any],
    ) -> ManualOutreachQueue:
        task = await self._manual.get_or_404(organization_id, task_id)
        for field in (
            "status",
            "priority",
            "due_at",
            "subject",
            "body",
            "notes",
            "assigned_user_id",
            "completed_at",
        ):
            if field in data:
                setattr(task, field, data[field])
        await commit_with_retry(self._session)
        return task
