"""Founder action proposal repository (org-scoped, approval-gated actions)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.enums import FounderProposalStatus
from app.models.founder_action_proposal import FounderActionProposal
from app.repositories.base import TenantRepository

if TYPE_CHECKING:
    pass

# Guarded lifecycle. Terminal states cannot be left; only the edges below are
# legal. Enforced by :meth:`FounderActionProposalRepository.apply_transition`.
_PROPOSAL_TRANSITIONS: dict[FounderProposalStatus, frozenset[FounderProposalStatus]] = {
    FounderProposalStatus.PROPOSED: frozenset(
        {
            FounderProposalStatus.APPROVED,
            FounderProposalStatus.DENIED,
            FounderProposalStatus.EXPIRED,
            FounderProposalStatus.CANCELLED,
        }
    ),
    FounderProposalStatus.APPROVED: frozenset({FounderProposalStatus.EXECUTING}),
    FounderProposalStatus.EXECUTING: frozenset(
        {FounderProposalStatus.SUCCEEDED, FounderProposalStatus.FAILED}
    ),
}


class FounderActionProposalRepository(TenantRepository[FounderActionProposal]):
    """Data access for founder action proposals (org-scoped)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FounderActionProposal)

    async def list_by_status(
        self,
        organization_id: uuid.UUID,
        *,
        status: FounderProposalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FounderActionProposal]:
        """List proposals, optionally by status, newest first."""
        stmt = select(FounderActionProposal).where(
            FounderActionProposal.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(FounderActionProposal.proposal_status == status)
        stmt = stmt.order_by(FounderActionProposal.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(
        self,
        organization_id: uuid.UUID,
        *,
        status: FounderProposalStatus | None = None,
    ) -> int:
        """Count proposals with the same org/status filters as ``list_by_status``."""
        stmt = select(func.count(FounderActionProposal.id)).where(
            FounderActionProposal.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(FounderActionProposal.proposal_status == status)
        result = await self._session.execute(stmt.select_from(FounderActionProposal))
        return int(result.scalar_one())

    async def list_by_conversation(
        self,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[FounderActionProposal]:
        """Proposals spawned by a given conversation, newest first."""
        stmt = (
            select(FounderActionProposal)
            .where(
                FounderActionProposal.organization_id == organization_id,
                FounderActionProposal.conversation_id == conversation_id,
            )
            .order_by(FounderActionProposal.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_expired(
        self, organization_id: uuid.UUID, *, now: datetime, limit: int = 200
    ) -> list[FounderActionProposal]:
        """Open (PROPOSED) proposals whose ``expires_at`` is in the past."""
        stmt = (
            select(FounderActionProposal)
            .where(
                FounderActionProposal.organization_id == organization_id,
                FounderActionProposal.proposal_status == FounderProposalStatus.PROPOSED,
                FounderActionProposal.expires_at.is_not(None),
                FounderActionProposal.expires_at < now,
            )
            .order_by(FounderActionProposal.expires_at)
            .limit(min(limit, 500))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_expired_all(
        self, *, now: datetime, limit: int = 500
    ) -> list[FounderActionProposal]:
        """All open proposals (any org) whose ``expires_at`` is in the past."""
        stmt = (
            select(FounderActionProposal)
            .where(
                FounderActionProposal.proposal_status == FounderProposalStatus.PROPOSED,
                FounderActionProposal.expires_at.is_not(None),
                FounderActionProposal.expires_at < now,
            )
            .order_by(FounderActionProposal.expires_at)
            .limit(min(limit, 1000))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def is_terminal(status: FounderProposalStatus) -> bool:
        """Whether a status admits no further transitions."""
        return status not in _PROPOSAL_TRANSITIONS

    def apply_transition(
        self,
        proposal: FounderActionProposal,
        new_status: FounderProposalStatus,
        *,
        now: datetime,
        decided_by_user_id: uuid.UUID | None = None,
    ) -> None:
        """Mutate ``proposal_status`` only along a legal edge; else raise.

        Stamps ``decided_at`` for terminal decisions. The caller owns the
        transaction (commit/rollback).
        """
        current = proposal.proposal_status
        if current == new_status:
            return
        allowed = _PROPOSAL_TRANSITIONS.get(current, frozenset())
        if new_status not in allowed:
            raise AppError(
                code="founder_proposal.invalid_transition",
                message=(
                    f"cannot transition proposal {proposal.id} "
                    f"from {current.value} to {new_status.value}"
                ),
                status_code=409,
            )
        proposal.proposal_status = new_status
        if new_status in (
            FounderProposalStatus.APPROVED,
            FounderProposalStatus.DENIED,
            FounderProposalStatus.EXPIRED,
            FounderProposalStatus.CANCELLED,
            FounderProposalStatus.SUCCEEDED,
            FounderProposalStatus.FAILED,
        ):
            proposal.decided_at = now
            proposal.decided_by_user_id = decided_by_user_id or proposal.decided_by_user_id

    # -- atomic decision/execution claims --------------------------------
    #
    # These are conditional ``UPDATE ... RETURNING`` statements: the row is
    # claimed by whichever transaction changes it first. A loser sees no row
    # and must not execute any side effect. Unlike ``apply_transition`` (an
    # in-memory guard for local consistency), these claims are the concurrency
    # boundary and need no schema change.

    async def claim_decision(
        self,
        organization_id: uuid.UUID,
        proposal_id: uuid.UUID,
        *,
        target: FounderProposalStatus,
        now: datetime,
        decided_by_user_id: uuid.UUID,
    ) -> bool:
        """Atomically claim ``PROPOSED -> APPROVED|DENIED``; False if lost."""
        if target not in (
            FounderProposalStatus.APPROVED,
            FounderProposalStatus.DENIED,
        ):
            raise ValueError(f"invalid decision target {target!r}")
        stmt = (
            update(FounderActionProposal)
            .where(
                FounderActionProposal.organization_id == organization_id,
                FounderActionProposal.id == proposal_id,
                FounderActionProposal.proposal_status == FounderProposalStatus.PROPOSED,
            )
            .values(
                proposal_status=target,
                decided_at=now,
                decided_by_user_id=decided_by_user_id,
            )
            .execution_options(synchronize_session=False)
            .returning(FounderActionProposal.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def claim_execution(
        self,
        organization_id: uuid.UUID,
        proposal_id: uuid.UUID,
        *,
        now: datetime,
        decided_by_user_id: uuid.UUID,
    ) -> bool:
        """Atomically claim ``APPROVED -> EXECUTING``; only one caller wins."""
        stmt = (
            update(FounderActionProposal)
            .where(
                FounderActionProposal.organization_id == organization_id,
                FounderActionProposal.id == proposal_id,
                FounderActionProposal.proposal_status == FounderProposalStatus.APPROVED,
            )
            .values(
                proposal_status=FounderProposalStatus.EXECUTING,
                decided_at=now,
                decided_by_user_id=decided_by_user_id,
            )
            .execution_options(synchronize_session=False)
            .returning(FounderActionProposal.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def finish_execution(
        self,
        organization_id: uuid.UUID,
        proposal_id: uuid.UUID,
        *,
        status: FounderProposalStatus,
        now: datetime,
        decided_by_user_id: uuid.UUID,
        reference: dict | None = None,
    ) -> bool:
        """Atomically settle ``EXECUTING -> SUCCEEDED|FAILED``; False if lost."""
        if status not in (
            FounderProposalStatus.SUCCEEDED,
            FounderProposalStatus.FAILED,
        ):
            raise ValueError(f"invalid execution result {status!r}")
        stmt = (
            update(FounderActionProposal)
            .where(
                FounderActionProposal.organization_id == organization_id,
                FounderActionProposal.id == proposal_id,
                FounderActionProposal.proposal_status == FounderProposalStatus.EXECUTING,
            )
            .values(
                proposal_status=status,
                decided_at=now,
                decided_by_user_id=decided_by_user_id,
                execution_reference=reference,
            )
            .execution_options(synchronize_session=False)
            .returning(FounderActionProposal.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_expired(
        self,
        organization_id: uuid.UUID,
        proposal_id: uuid.UUID,
        *,
        now: datetime,
    ) -> bool:
        """Transition a PROPOSED proposal to EXPIRED; False when not PROPOSED."""
        stmt = (
            update(FounderActionProposal)
            .where(
                FounderActionProposal.organization_id == organization_id,
                FounderActionProposal.id == proposal_id,
                FounderActionProposal.proposal_status == FounderProposalStatus.PROPOSED,
            )
            .values(
                proposal_status=FounderProposalStatus.EXPIRED,
                decided_at=now,
            )
        )
        result = await self._session.execute(stmt)
        return (cast(CursorResult, result).rowcount or 0) > 0
