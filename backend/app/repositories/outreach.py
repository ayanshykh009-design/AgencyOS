"""Outreach repositories: message templates, attempts, follow-ups, manual queue."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import OutreachStatus
from app.models.follow_up import FollowUp
from app.models.manual_outreach_queue import ManualOutreachQueue
from app.models.outreach_attempt import OutreachAttempt
from app.models.outreach_message import OutreachMessage


class OutreachMessageRepository:
    """Data access for reusable message templates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: uuid.UUID, message_id: uuid.UUID
    ) -> OutreachMessage | None:
        message = await self._session.get(OutreachMessage, message_id)
        if message is None or message.organization_id != organization_id:
            return None
        return message

    async def get_or_404(
        self, organization_id: uuid.UUID, message_id: uuid.UUID
    ) -> OutreachMessage:
        message = await self.get(organization_id, message_id)
        if message is None:
            raise AppError(
                code="outreach_message.not_found",
                message="Outreach message not found",
                status_code=404,
            )
        return message

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        channel=None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OutreachMessage]:
        stmt = select(OutreachMessage).where(
            OutreachMessage.organization_id == organization_id
        )
        if channel is not None:
            stmt = stmt.where(OutreachMessage.channel == channel)
        stmt = stmt.order_by(OutreachMessage.name).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, message: OutreachMessage) -> None:
        self._session.add(message)

    @staticmethod
    async def handle_integrity_error(exc: IntegrityError) -> None:
        raise AppError(
            code="outreach_message.duplicate",
            message="An outreach message with that name already exists",
            status_code=409,
        ) from exc


class OutreachAttemptRepository:
    """Data access for outreach attempts (per-lead sends)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> OutreachAttempt | None:
        attempt = await self._session.get(OutreachAttempt, attempt_id)
        if attempt is None or attempt.organization_id != organization_id:
            return None
        return attempt

    async def get_or_404(
        self, organization_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> OutreachAttempt:
        attempt = await self.get(organization_id, attempt_id)
        if attempt is None:
            raise AppError(
                code="outreach_attempt.not_found",
                message="Outreach attempt not found",
                status_code=404,
            )
        return attempt

    async def list_for_lead(
        self,
        organization_id: uuid.UUID,
        lead_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OutreachAttempt]:
        stmt = (
            select(OutreachAttempt)
            .where(
                OutreachAttempt.organization_id == organization_id,
                OutreachAttempt.lead_id == lead_id,
            )
            .order_by(OutreachAttempt.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_outstanding(self, organization_id: uuid.UUID) -> int:
        """Count queued/sending attempts (dashboard metric)."""
        stmt = (
            select(func.count(OutreachAttempt.id))
            .where(
                OutreachAttempt.organization_id == organization_id,
                OutreachAttempt.status.in_(
                    [OutreachStatus.QUEUED, OutreachStatus.SENDING]
                ),
            )
            .select_from(OutreachAttempt)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def add(self, attempt: OutreachAttempt) -> None:
        self._session.add(attempt)


class FollowUpRepository:
    """Data access for scheduled follow-ups."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: uuid.UUID, follow_up_id: uuid.UUID
    ) -> FollowUp | None:
        follow_up = await self._session.get(FollowUp, follow_up_id)
        if follow_up is None or follow_up.organization_id != organization_id:
            return None
        return follow_up

    async def get_or_404(
        self, organization_id: uuid.UUID, follow_up_id: uuid.UUID
    ) -> FollowUp:
        follow_up = await self.get(organization_id, follow_up_id)
        if follow_up is None:
            raise AppError(
                code="follow_up.not_found",
                message="Follow-up not found",
                status_code=404,
            )
        return follow_up

    async def list_for_lead(
        self, organization_id: uuid.UUID, lead_id: uuid.UUID
    ) -> list[FollowUp]:
        stmt = (
            select(FollowUp)
            .where(
                FollowUp.organization_id == organization_id,
                FollowUp.lead_id == lead_id,
            )
            .order_by(FollowUp.sequence_position)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, follow_up: FollowUp) -> None:
        self._session.add(follow_up)


class ManualOutreachQueueRepository:
    """Data access for manual outreach tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> ManualOutreachQueue | None:
        task = await self._session.get(ManualOutreachQueue, task_id)
        if task is None or task.organization_id != organization_id:
            return None
        return task

    async def get_or_404(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> ManualOutreachQueue:
        task = await self.get(organization_id, task_id)
        if task is None:
            raise AppError(
                code="manual_outreach_queue.not_found",
                message="Manual outreach task not found",
                status_code=404,
            )
        return task

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        status: OutreachStatus | None = None,
        assigned_user_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ManualOutreachQueue]:
        stmt = select(ManualOutreachQueue).where(
            ManualOutreachQueue.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(ManualOutreachQueue.status == status)
        if assigned_user_id is not None:
            stmt = stmt.where(ManualOutreachQueue.assigned_user_id == assigned_user_id)
        stmt = stmt.order_by(ManualOutreachQueue.priority.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def add(self, task: ManualOutreachQueue) -> None:
        self._session.add(task)
