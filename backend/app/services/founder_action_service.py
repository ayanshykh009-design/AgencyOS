"""Founder action service — every assistant action is gated and logged.

The founder assistant never mutates org data directly. This service is the only
write path: :meth:`propose` records a :class:`FounderActionProposal` and links it
to a shared :class:`ApprovalRequest` (single source of truth for gating). Only
after that request is approved does :meth:`decide_proposal` execute the action.

Transitions on the proposal are guarded (see
``FounderActionProposalRepository.apply_transition``); terminal states are
immutable.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.models.enums import FounderActionType, FounderProposalStatus, TaskPriority, TaskStatus
from app.models.founder_action_proposal import FounderActionProposal
from app.models.task import Task
from app.models.user import User
from app.repositories.approval_request import ApprovalRequestRepository
from app.repositories.founder_action_proposal import FounderActionProposalRepository
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.services.approval_service import ApprovalService
from app.services.base import commit_with_retry, utcnow

logger = logging.getLogger("agencyos.founder.action")


class FounderActionService:
    """Owns founder-proposal rules and the transaction boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proposals = FounderActionProposalRepository(session)

    # -- reads ----------------------------------------------------------

    async def list_proposals(
        self,
        organization_id: uuid.UUID,
        *,
        status: FounderProposalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FounderActionProposal]:
        return await self._proposals.list_by_status(
            organization_id, status=status, limit=limit, offset=offset
        )

    async def get_proposal(
        self, organization_id: uuid.UUID, proposal_id: uuid.UUID
    ) -> FounderActionProposal:
        proposal = await self._proposals.get(organization_id, proposal_id)
        if proposal is None:
            raise AppError(
                code="founder_proposal.not_found",
                message="Founder proposal not found",
                status_code=404,
            )
        return proposal

    async def count_proposals(
        self,
        organization_id: uuid.UUID,
        *,
        status: FounderProposalStatus | None = None,
    ) -> int:
        """True filtered count for ``list_proposals`` pagination."""
        return await self._proposals.count_by_status(organization_id, status=status)

    # -- propose --------------------------------------------------------

    async def propose(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        conversation_id: uuid.UUID | None,
        action_type: FounderActionType,
        title: str,
        payload: dict[str, Any],
        justification: str | None = None,
    ) -> FounderActionProposal:
        """Record a proposal and link it to a pending approval request."""
        if not isinstance(action_type, FounderActionType):
            action_type = FounderActionType(action_type)
        actor = await self._load_actor(actor_user_id)
        expires_at = utcnow() + timedelta(seconds=settings.FOUNDER_APPROVAL_TTL_SECONDS)

        approval = await ApprovalService(self._session).create_request(
            organization_id=organization_id,
            requested_by_user_id=actor.id,
            actor=actor,
            workflow_id=None,
            workflow_execution_id=None,
            approver_user_id=actor.id,
            title=f"[Founder] {title}",
            details=json.dumps({"action_type": action_type.value, "payload": payload}, default=str),
            expires_at=expires_at,
        )

        proposal = FounderActionProposal(
            organization_id=organization_id,
            conversation_id=conversation_id,
            approval_request_id=approval.id,
            proposal_status=FounderProposalStatus.PROPOSED,
            action_type=action_type,
            title=title,
            payload=payload,
            justification=justification,
            expires_at=expires_at,
            actor_user_id=actor.id,
        )
        self._proposals.add(proposal)
        await commit_with_retry(self._session)
        return proposal

    # -- decide ---------------------------------------------------------

    async def decide_proposal(
        self,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        proposal_id: uuid.UUID,
        *,
        approve: bool,
        decision_note: str | None = None,
    ) -> FounderActionProposal:
        """Approve or deny a proposal; on approval, execute the action once.

        The decision (shared approval request + proposal status) is claimed in
        a single transaction via conditional updates, so concurrent requests
        cannot both win. Execution is a separate, idempotent saga step: only
        the caller that atomically claims ``APPROVED -> EXECUTING`` performs
        the side effect, and a lost claim never re-runs it.
        """
        proposal = await self.get_proposal(organization_id, proposal_id)

        # Per-org AI kill switch (F-SEC-3): block execution of approved founder
        # actions while the organization's AI execution is disabled.
        from app.services.ai_service import AIService

        await AIService(self._session).assert_ai_enabled(organization_id)

        if proposal.proposal_status != FounderProposalStatus.PROPOSED:
            raise AppError(
                code="founder_proposal.not_pending",
                message=f"proposal is {proposal.proposal_status.value}, not pending",
                status_code=409,
            )
        # Enforce the approval time-box at the synchronous gate, not only in the
        # background sweep. Without this an expired-but-still-PROPOSED proposal can
        # be approved (and executed) if the worker is not deployed or between runs.
        now = utcnow()
        if proposal.expires_at is not None and now > proposal.expires_at:
            expired = await self._expire_pair(organization_id, proposal, now=now)
            if not expired:
                # A concurrent decision won the approval claim. Fail closed
                # instead of expiring a proposal that may already be decided.
                await self._session.rollback()
                current = await self._proposals.get(organization_id, proposal.id)
                if current is None or current.proposal_status is not FounderProposalStatus.EXPIRED:
                    raise AppError(
                        code="founder_proposal.not_pending",
                        message="proposal state changed concurrently",
                        status_code=409,
                    )
            else:
                await commit_with_retry(self._session)
            raise AppError(
                code="founder_proposal.expired",
                message="This proposal has expired and can no longer be approved",
                status_code=409,
            )
        if proposal.approval_request_id is None:
            raise AppError(
                code="founder_proposal.no_approval",
                message="proposal has no linked approval request",
                status_code=409,
            )

        actor = await self._load_actor(actor_user_id)
        target = FounderProposalStatus.APPROVED if approve else FounderProposalStatus.DENIED
        try:
            # Approval decision and proposal transition share one transaction:
            # a crash cannot leave the approval decided and the proposal stuck.
            await ApprovalService(self._session).decide(
                organization_id,
                actor=actor,
                request_id=proposal.approval_request_id,
                approve=approve,
                decision_note=decision_note,
                commit=False,
            )
            if not await self._proposals.claim_decision(
                organization_id,
                proposal.id,
                target=target,
                now=now,
                decided_by_user_id=actor.id,
            ):
                raise AppError(
                    code="founder_proposal.not_pending",
                    message="proposal was decided concurrently",
                    status_code=409,
                )
            self._proposals.apply_transition(proposal, target, now=now, decided_by_user_id=actor.id)
            await commit_with_retry(self._session)
        except Exception:
            await self._session.rollback()
            raise

        if not approve:
            return proposal

        # Execution saga: claim first, re-check, then perform the side effect.
        if not await self._proposals.claim_execution(
            organization_id,
            proposal.id,
            now=utcnow(),
            decided_by_user_id=actor.id,
        ):
            # A concurrent request already claimed/settled this proposal.
            # Never create a second task; report the settled state if terminal.
            current = await self._proposals.get(organization_id, proposal.id)
            if current is not None and self._proposals.is_terminal(current.proposal_status):
                return current
            raise AppError(
                code="founder_proposal.not_pending",
                message="proposal execution was claimed concurrently",
                status_code=409,
            )
        self._proposals.apply_transition(
            proposal,
            FounderProposalStatus.EXECUTING,
            now=utcnow(),
            decided_by_user_id=actor.id,
        )
        await commit_with_retry(self._session)

        # Re-check the claimed state immediately before any side effect.
        current = await self._proposals.get(organization_id, proposal.id)
        if current is None or current.proposal_status is not FounderProposalStatus.EXECUTING:
            raise AppError(
                code="founder_proposal.not_pending",
                message="proposal is no longer executing",
                status_code=409,
            )

        try:
            reference = await self._execute(proposal, actor=actor)
        except Exception as exc:  # noqa: BLE001 - record failure, keep proposal auditable
            logger.exception("founder proposal %s execution failed", proposal.id)
            error_code = (
                exc.code if isinstance(exc, AppError) else "founder_proposal.execution_failed"
            )
            reference = {"error": "execution failed; see logs", "code": error_code}
            await self._settle_execution(
                organization_id,
                proposal,
                status=FounderProposalStatus.FAILED,
                now=utcnow(),
                actor=actor,
                reference=reference,
            )
            self._proposals.apply_transition(
                proposal,
                FounderProposalStatus.FAILED,
                now=utcnow(),
                decided_by_user_id=actor.id,
            )
            proposal.execution_reference = reference
            await commit_with_retry(self._session)
            return proposal
        await self._settle_execution(
            organization_id,
            proposal,
            status=FounderProposalStatus.SUCCEEDED,
            now=utcnow(),
            actor=actor,
            reference=reference,
        )
        self._proposals.apply_transition(
            proposal,
            FounderProposalStatus.SUCCEEDED,
            now=utcnow(),
            decided_by_user_id=actor.id,
        )
        proposal.execution_reference = reference
        await commit_with_retry(self._session)
        return proposal

    async def _settle_execution(
        self,
        organization_id: uuid.UUID,
        proposal: FounderActionProposal,
        *,
        status: FounderProposalStatus,
        now: datetime,
        actor: User,
        reference: dict[str, Any],
    ) -> None:
        """Claim the final terminal state; fail closed if another actor won."""
        settled = await self._proposals.finish_execution(
            organization_id,
            proposal.id,
            status=status,
            now=now,
            decided_by_user_id=actor.id,
            reference=reference,
        )
        if not settled:
            # The proposal is no longer EXECUTING. Roll back any local side
            # effect from this attempt instead of reporting a state we do not
            # own, and surface the conflict to the caller.
            await self._session.rollback()
            raise AppError(
                code="founder_proposal.not_pending",
                message="proposal execution was settled concurrently",
                status_code=409,
            )

    # -- expiry sweep ---------------------------------------------------

    async def _expire_pair(
        self,
        organization_id: uuid.UUID,
        proposal: FounderActionProposal,
        *,
        now: datetime,
    ) -> bool:
        """Expire the linked approval first, then the proposal.

        Every path that touches both rows locks them approval-first. The
        decision path already does this through ``ApprovalService.decide``;
        following the same order here prevents an expiry/decision deadlock.
        Both conditional updates must claim a row for the pair to count.
        """
        approvals = ApprovalRequestRepository(self._session)
        if proposal.approval_request_id is not None:
            if not await approvals.mark_expired(
                organization_id, proposal.approval_request_id, now=now
            ):
                return False
        return await self._proposals.mark_expired(organization_id, proposal.id, now=now)

    async def expire_due(self, organization_id: uuid.UUID, *, now: datetime | None = None) -> int:
        """Expire PROPOSED proposals past their ``expires_at`` (and their approvals)."""
        now = now or utcnow()
        due = await self._proposals.list_pending_expired(organization_id, now=now)
        if not due:
            return 0
        handled = 0
        for proposal in due:
            if await self._expire_pair(organization_id, proposal, now=now):
                handled += 1
        if handled:
            await commit_with_retry(self._session)
        return handled

    async def expire_due_all(self, *, now: datetime | None = None) -> int:
        """Global sweep: expire every org's PROPOSED proposals past ``expires_at``."""
        now = now or utcnow()
        due = await self._proposals.list_pending_expired_all(now=now)
        if not due:
            return 0
        by_org: dict[uuid.UUID, list[FounderActionProposal]] = {}
        for proposal in due:
            by_org.setdefault(proposal.organization_id, []).append(proposal)
        handled = 0
        for org_id, items in by_org.items():
            for proposal in items:
                if await self._expire_pair(org_id, proposal, now=now):
                    handled += 1
        if handled:
            await commit_with_retry(self._session)
        return handled

    # -- internals ------------------------------------------------------

    async def _load_actor(self, actor_user_id: uuid.UUID | None) -> User:
        if actor_user_id is None:
            raise AppError(
                code="founder_proposal.no_actor",
                message="a founder user is required to act",
                status_code=400,
            )
        user = await UserRepository(self._session).get(actor_user_id)
        if user is None:
            raise AppError(
                code="founder_proposal.actor_unknown",
                message="actor user not found",
                status_code=404,
            )
        return user

    async def _execute(self, proposal: FounderActionProposal, *, actor: User) -> dict[str, Any]:
        """Execute an approved proposal. Returns an execution reference dict."""
        if proposal.action_type == FounderActionType.CREATE_TASK:
            return await self._execute_create_task(proposal, actor=actor)
        # Other action types are owned by their respective subsystems
        # (delivery / workflow / export). The approval gate — the M8 deliverable
        # — is the single source of truth; downstream dispatch happens there.
        return {
            "handled_by": "subsystem",
            "action_type": proposal.action_type.value,
            "note": "approved; dispatched to the owning subsystem",
        }

    async def _execute_create_task(
        self, proposal: FounderActionProposal, *, actor: User
    ) -> dict[str, Any]:
        payload = proposal.payload or {}
        raw_priority = (payload.get("priority") or "medium").lower()
        try:
            priority = TaskPriority(raw_priority)
        except ValueError:
            priority = TaskPriority.MEDIUM

        due_at = None
        raw_due = payload.get("due_at")
        if raw_due:
            try:
                due_at = datetime.fromisoformat(str(raw_due).replace("Z", "+00:00"))
                if due_at.tzinfo is not None:
                    due_at = due_at.astimezone(UTC).replace(tzinfo=None)
            except (ValueError, TypeError):
                due_at = None

        assignee = None
        raw_assignee = payload.get("assignee_user_id")
        if raw_assignee:
            try:
                assignee_id = uuid.UUID(str(raw_assignee))
            except (ValueError, TypeError) as exc:
                # Never silently drop an invalid assignee and create an
                # unowned task; fail closed and let the proposal record the
                # (safe) execution error.
                raise AppError(
                    code="task.invalid_assignee",
                    message="Assignee is not a valid team member",
                    status_code=400,
                ) from exc
            # Same org-scoped, active-user policy as TaskService._validate_links.
            # A foreign/inactive/unknown id must not produce a task.
            users = UserRepository(self._session)
            assignee_user = await users.get_or_404(proposal.organization_id, assignee_id)
            if not assignee_user.is_active:
                raise AppError(
                    code="task.invalid_assignee",
                    message="Assignee is not an active team member",
                    status_code=400,
                )
            assignee = assignee_user.id

        task = Task(
            organization_id=proposal.organization_id,
            title=payload.get("title") or proposal.title,
            description=payload.get("description"),
            status=TaskStatus.TODO,
            priority=priority,
            due_at=due_at,
            assignee_user_id=assignee,
            created_by_user_id=actor.id,
        )
        TaskRepository(self._session).add(task)
        await self._session.flush()
        return {"task_id": str(task.id), "title": task.title}
