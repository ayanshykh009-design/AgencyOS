"""Approval service: gated workflow approvals + immutable audit log.

The approval *decision* flow is the API surface for approvals — recording the
request and the approve/deny transition plus its audit log. Gating workers and
notification delivery land in M6; this service owns the transactional state
machine (pending -> approved/denied/expired/cancelled).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.approval_log import ApprovalLog
from app.models.approval_request import ApprovalRequest
from app.models.enums import ApprovalLogAction, ApprovalRequestStatus
from app.models.user import User
from app.repositories.approval_log import ApprovalLogRepository
from app.repositories.approval_request import ApprovalRequestRepository
from app.services.base import commit_with_retry, utcnow


class ApprovalService:
    """Owns approval rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._requests = ApprovalRequestRepository(session)
        self._logs = ApprovalLogRepository(session)

    async def list_requests(
        self,
        organization_id: uuid.UUID,
        *,
        status: ApprovalRequestStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApprovalRequest]:
        return await self._requests.list_by_status(
            organization_id, status=status, limit=limit, offset=offset
        )

    async def get_request(
        self, organization_id: uuid.UUID, request_id: uuid.UUID
    ) -> ApprovalRequest:
        return await self._requests.get_or_404(organization_id, request_id)

    async def pending_count(self, organization_id: uuid.UUID) -> int:
        return await self._requests.count_pending(organization_id)

    async def create_request(
        self,
        organization_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
        actor: User,
        *,
        workflow_id: uuid.UUID | None,
        workflow_execution_id: uuid.UUID | None,
        approver_user_id: uuid.UUID | None,
        title: str,
        details: str | None,
        expires_at: datetime | None,
    ) -> ApprovalRequest:
        """Create a request and append the initial ``requested`` audit log.

        ``expires_at`` is omitted (not set to NULL) when absent so the database
        default (``now() + APPROVAL_EXPIRY_HOURS``) applies.
        """
        values: dict[str, Any] = {
            "organization_id": organization_id,
            "workflow_id": workflow_id,
            "workflow_execution_id": workflow_execution_id,
            "requested_by_user_id": requested_by_user_id,
            "approver_user_id": approver_user_id,
            "title": title,
            "details": details,
        }
        if expires_at is not None:
            values["expires_at"] = expires_at
        request = ApprovalRequest(**values)
        self._requests.add(request)
        self._logs.add(
            ApprovalLog(
                organization_id=organization_id,
                approval_request_id=request.id,
                actor_user_id=requested_by_user_id,
                action=ApprovalLogAction.REQUESTED,
            )
        )
        await commit_with_retry(self._session)
        return request

    async def decide(
        self,
        organization_id: uuid.UUID,
        actor: User,
        request_id: uuid.UUID,
        *,
        approve: bool,
        decided_by_user_id: uuid.UUID | None,
        decision_note: str | None,
    ) -> ApprovalRequest:
        """Transition a pending request to approved/denied and log the decision."""
        request = await self._requests.get_or_404(organization_id, request_id)
        if request.status is not ApprovalRequestStatus.PENDING:
            raise AppError(
                code="approval.not_pending",
                message="Approval request is not pending",
                status_code=409,
            )
        # Enforce the approval time-box at the synchronous gate (not only in the
        # background sweep). A PENDING request past its expires_at must be rejected.
        now = utcnow()
        if request.expires_at is not None and now > request.expires_at:
            await self._requests.mark_expired(organization_id, request.id, now=now)
            await commit_with_retry(self._session)
            raise AppError(
                code="approval.expired",
                message="Approval request has expired and can no longer be decided",
                status_code=409,
            )
        action = ApprovalLogAction.APPROVED if approve else ApprovalLogAction.DENIED
        request.status = ApprovalRequestStatus.APPROVED if approve else ApprovalRequestStatus.DENIED
        request.decided_by_user_id = decided_by_user_id or actor.id
        request.decided_at = utcnow()
        request.decision_note = decision_note
        self._logs.add(
            ApprovalLog(
                organization_id=organization_id,
                approval_request_id=request.id,
                actor_user_id=actor.id,
                action=action,
                note=decision_note,
            )
        )
        await commit_with_retry(self._session)
        return request

    async def list_logs(
        self,
        organization_id: uuid.UUID,
        request_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        await self._requests.get_or_404(organization_id, request_id)
        return await self._logs.list_by_request(
            organization_id, request_id, limit=limit, offset=offset
        )
