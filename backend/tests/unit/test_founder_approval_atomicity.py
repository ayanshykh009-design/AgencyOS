"""Concurrency/validation regressions for founder proposal decisions.

These tests use in-memory fakes (no DB fixtures): the point is to prove that
the guarded conditional updates are the decision boundary, that a stale
snapshot cannot execute an action twice, and that an untrusted assignee id
never creates a task.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AppError
from app.models.enums import (
    ApprovalRequestStatus,
    FounderActionType,
    FounderProposalStatus,
)
from app.services.approval_service import ApprovalService
from app.services.founder_action_service import FounderActionService

ORG = uuid.uuid4()
ACTOR_ID = uuid.uuid4()
REQ_ID = uuid.uuid4()
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _result(claimed: bool) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4() if claimed else None
    return result


def _pending_request() -> SimpleNamespace:
    return SimpleNamespace(
        id=REQ_ID,
        organization_id=ORG,
        status=ApprovalRequestStatus.PENDING,
        expires_at=None,
        decided_by_user_id=None,
        decided_at=None,
        decision_note=None,
    )


# -- approval decision claim ------------------------------------------


async def test_approval_decide_claims_with_guarded_update() -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(True))
    requests = MagicMock()
    request = _pending_request()
    requests.get_or_404 = AsyncMock(return_value=request)
    logs = MagicMock()
    service = ApprovalService(session)
    service._requests = requests
    service._logs = logs

    with patch("app.services.approval_service.commit_with_retry", new_callable=AsyncMock) as commit:
        result = await service.decide(
            ORG, SimpleNamespace(id=ACTOR_ID), REQ_ID, approve=True, decision_note="ok"
        )

    session.execute.assert_awaited_once()
    stmt = session.execute.await_args.args[0]
    # Status/expiry guards are in the UPDATE itself; RETURNING proves the row
    # was actually claimed instead of assumed from an earlier SELECT.
    assert stmt.table.name == "approval_requests"
    assert len(stmt._where_criteria) == 4
    assert stmt._returning
    assert any(
        getattr(value, "value", None) is ApprovalRequestStatus.APPROVED
        for value in stmt._values.values()
    )
    assert result.status is ApprovalRequestStatus.APPROVED
    assert result.decided_by_user_id == ACTOR_ID
    logs.add.assert_called_once()
    commit.assert_awaited_once()


async def test_approval_decide_loser_writes_no_log_and_does_not_commit() -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(False))  # concurrent winner
    requests = MagicMock()
    requests.get_or_404 = AsyncMock(return_value=_pending_request())
    logs = MagicMock()
    service = ApprovalService(session)
    service._requests = requests
    service._logs = logs

    with patch("app.services.approval_service.commit_with_retry", new_callable=AsyncMock) as commit:
        with pytest.raises(AppError) as exc:
            await service.decide(ORG, SimpleNamespace(id=ACTOR_ID), REQ_ID, approve=True)

    assert exc.value.code == "approval.not_pending"
    assert exc.value.status_code == 409
    logs.add.assert_not_called()
    commit.assert_not_awaited()


async def test_approval_decide_can_defer_commit_to_caller() -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(True))
    requests = MagicMock()
    requests.get_or_404 = AsyncMock(return_value=_pending_request())
    service = ApprovalService(session)
    service._requests = requests
    service._logs = MagicMock()

    with patch("app.services.approval_service.commit_with_retry", new_callable=AsyncMock) as commit:
        await service.decide(ORG, SimpleNamespace(id=ACTOR_ID), REQ_ID, approve=False, commit=False)
    commit.assert_not_awaited()


# -- founder decision race / execution idempotency --------------------


class _RacyProposals:
    """One in-memory row guarded exactly like the DB conditional updates."""

    def __init__(self) -> None:
        self.status = FounderProposalStatus.PROPOSED
        self.finish_calls: list[tuple[FounderProposalStatus, dict | None]] = []

    async def get(self, organization_id, proposal_id):
        return SimpleNamespace(
            id=proposal_id,
            organization_id=organization_id,
            proposal_status=self.status,
            expires_at=None,
            approval_request_id=REQ_ID,
            action_type=FounderActionType.CREATE_TASK,
            payload={"title": "Follow up"},
            execution_reference=None,
            decided_by_user_id=None,
        )

    async def claim_decision(
        self, organization_id, proposal_id, *, target, now, decided_by_user_id
    ):
        if self.status is not FounderProposalStatus.PROPOSED:
            return False
        self.status = target
        return True

    def apply_transition(self, proposal, new_status, *, now, decided_by_user_id=None):
        proposal.proposal_status = new_status
        self.status = new_status

    async def claim_execution(self, organization_id, proposal_id, *, now, decided_by_user_id):
        if self.status is not FounderProposalStatus.APPROVED:
            return False
        self.status = FounderProposalStatus.EXECUTING
        return True

    async def finish_execution(
        self, organization_id, proposal_id, *, status, now, decided_by_user_id, reference=None
    ):
        if self.status is not FounderProposalStatus.EXECUTING:
            return False
        self.status = status
        self.finish_calls.append((status, reference))
        return True

    @staticmethod
    def is_terminal(status: FounderProposalStatus) -> bool:
        return status in (
            FounderProposalStatus.DENIED,
            FounderProposalStatus.EXPIRED,
            FounderProposalStatus.CANCELLED,
            FounderProposalStatus.SUCCEEDED,
            FounderProposalStatus.FAILED,
        )

    async def mark_expired(self, organization_id, proposal_id, *, now) -> bool:
        return False


class _RacyApprovals:
    def __init__(self) -> None:
        self.status = ApprovalRequestStatus.PENDING
        self.calls = 0

    async def decide(self, organization_id, *, actor, request_id, approve, decision_note, commit):
        assert commit is False, "founder decision must share the proposal transaction"
        self.calls += 1
        if self.status is not ApprovalRequestStatus.PENDING:
            raise AppError("approval.not_pending", "not pending", 409)
        self.status = ApprovalRequestStatus.APPROVED if approve else ApprovalRequestStatus.DENIED


def _patch_founder_flow(monkeypatch, proposals: _RacyProposals, approvals: _RacyApprovals):
    session = MagicMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    monkeypatch.setattr("app.services.ai_service.AIService.assert_ai_enabled", AsyncMock())
    monkeypatch.setattr(
        "app.services.founder_action_service.UserRepository",
        MagicMock(
            return_value=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=ACTOR_ID, is_active=True))
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.founder_action_service.ApprovalService",
        MagicMock(return_value=approvals),
    )
    monkeypatch.setattr(
        "app.services.founder_action_service.FounderActionProposalRepository",
        MagicMock(return_value=proposals),
    )
    monkeypatch.setattr("app.services.founder_action_service.commit_with_retry", AsyncMock())
    tasks = MagicMock()
    tasks.add = MagicMock()
    monkeypatch.setattr(
        "app.services.founder_action_service.TaskRepository", MagicMock(return_value=tasks)
    )
    monkeypatch.setattr("app.services.founder_action_service.utcnow", lambda: NOW)
    return session, tasks


async def test_stale_second_approval_cannot_create_second_task(monkeypatch) -> None:
    proposals, approvals = _RacyProposals(), _RacyApprovals()
    session, tasks = _patch_founder_flow(monkeypatch, proposals, approvals)
    service = FounderActionService(session)

    winner = await service.decide_proposal(ORG, ACTOR_ID, uuid.uuid4(), approve=True)
    assert winner.proposal_status is FounderProposalStatus.SUCCEEDED
    assert tasks.add.call_count == 1

    # A second request that loaded its proposal before the first committed
    # must lose the guarded approval claim even though its snapshot says PROPOSED.
    stale = await proposals.get(ORG, uuid.uuid4())
    stale.proposal_status = FounderProposalStatus.PROPOSED  # pre-decision snapshot
    service.get_proposal = AsyncMock(return_value=stale)
    with pytest.raises(AppError) as exc:
        await service.decide_proposal(ORG, ACTOR_ID, uuid.uuid4(), approve=True)
    assert exc.value.code == "approval.not_pending"
    assert tasks.add.call_count == 1
    assert approvals.calls == 2
    session.rollback.assert_awaited_once()


async def test_execution_claim_loser_never_executes(monkeypatch) -> None:
    proposals, approvals = _RacyProposals(), _RacyApprovals()
    session, tasks = _patch_founder_flow(monkeypatch, proposals, approvals)
    service = FounderActionService(session)
    service._execute = AsyncMock()

    reads = 0

    async def _get(org, pid):
        nonlocal reads
        reads += 1
        # First read is the caller's pre-decision snapshot; the post-claim
        # re-read sees the winner's terminal state.
        status = FounderProposalStatus.PROPOSED if reads == 1 else FounderProposalStatus.SUCCEEDED
        return SimpleNamespace(
            id=pid,
            organization_id=org,
            proposal_status=status,
            expires_at=None,
            approval_request_id=REQ_ID,
            action_type=FounderActionType.CREATE_TASK,
            payload={"title": "Follow up"},
            execution_reference=None,
            decided_by_user_id=None,
        )

    proposals.get = AsyncMock(side_effect=_get)
    proposals.claim_execution = AsyncMock(return_value=False)

    result = await service.decide_proposal(ORG, ACTOR_ID, uuid.uuid4(), approve=True)
    # The approval decision was claimed; execution was lost, so no side effect.
    assert result.proposal_status is FounderProposalStatus.SUCCEEDED
    service._execute.assert_not_awaited()
    tasks.add.assert_not_called()


async def test_lost_success_settlement_fails_closed(monkeypatch) -> None:
    proposals, approvals = _RacyProposals(), _RacyApprovals()
    session, _ = _patch_founder_flow(monkeypatch, proposals, approvals)
    service = FounderActionService(session)
    service._execute = AsyncMock(return_value={"task_id": str(uuid.uuid4())})
    proposals.finish_execution = AsyncMock(return_value=False)

    with pytest.raises(AppError) as exc:
        await service.decide_proposal(ORG, ACTOR_ID, uuid.uuid4(), approve=True)

    assert exc.value.code == "founder_proposal.not_pending"
    assert exc.value.status_code == 409
    assert proposals.status is FounderProposalStatus.EXECUTING
    session.rollback.assert_awaited_once()


async def test_lost_failure_settlement_fails_closed(monkeypatch) -> None:
    proposals, approvals = _RacyProposals(), _RacyApprovals()
    session, _ = _patch_founder_flow(monkeypatch, proposals, approvals)
    service = FounderActionService(session)
    service._execute = AsyncMock(side_effect=AppError("execution.failed", "failed", 500))
    proposals.finish_execution = AsyncMock(return_value=False)

    with pytest.raises(AppError) as exc:
        await service.decide_proposal(ORG, ACTOR_ID, uuid.uuid4(), approve=True)

    assert exc.value.code == "founder_proposal.not_pending"
    assert exc.value.status_code == 409
    assert proposals.status is FounderProposalStatus.EXECUTING
    session.rollback.assert_awaited_once()


async def test_synchronous_expiry_marks_linked_approval(monkeypatch) -> None:
    """Expiry must retire both rows, approval-first, to match decision locking."""
    proposals, approvals = _RacyProposals(), _RacyApprovals()
    session, _ = _patch_founder_flow(monkeypatch, proposals, approvals)
    order: list[str] = []

    async def _expire_approval(*args, **kwargs):
        order.append("approval")
        return True

    async def _expire_proposal(*args, **kwargs):
        order.append("proposal")
        return True

    proposals.mark_expired = AsyncMock(side_effect=_expire_proposal)
    approval_repo = MagicMock()
    approval_repo.mark_expired = AsyncMock(side_effect=_expire_approval)
    monkeypatch.setattr(
        "app.services.founder_action_service.ApprovalRequestRepository",
        MagicMock(return_value=approval_repo),
    )

    expired_id = uuid.uuid4()
    service = FounderActionService(session)
    service.get_proposal = AsyncMock(
        return_value=SimpleNamespace(
            id=expired_id,
            organization_id=ORG,
            proposal_status=FounderProposalStatus.PROPOSED,
            expires_at=NOW - timedelta(seconds=1),
            approval_request_id=REQ_ID,
        )
    )

    with pytest.raises(AppError) as exc:
        await service.decide_proposal(ORG, ACTOR_ID, expired_id, approve=True)

    assert exc.value.code == "founder_proposal.expired"
    assert exc.value.status_code == 409
    assert order == ["approval", "proposal"]
    proposals.mark_expired.assert_awaited_once_with(ORG, expired_id, now=NOW)
    approval_repo.mark_expired.assert_awaited_once_with(ORG, REQ_ID, now=NOW)


async def test_synchronous_expiry_lost_approval_claim_fails_closed(monkeypatch) -> None:
    """A concurrent decision must not be overwritten by the expiry gate."""
    proposals, approvals = _RacyProposals(), _RacyApprovals()
    session, _ = _patch_founder_flow(monkeypatch, proposals, approvals)
    proposals.mark_expired = AsyncMock(return_value=True)
    approval_repo = MagicMock()
    approval_repo.mark_expired = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.services.founder_action_service.ApprovalRequestRepository",
        MagicMock(return_value=approval_repo),
    )

    expired_id = uuid.uuid4()
    service = FounderActionService(session)
    service.get_proposal = AsyncMock(
        return_value=SimpleNamespace(
            id=expired_id,
            organization_id=ORG,
            proposal_status=FounderProposalStatus.PROPOSED,
            expires_at=NOW - timedelta(seconds=1),
            approval_request_id=REQ_ID,
        )
    )
    service._proposals.get = AsyncMock(
        return_value=SimpleNamespace(proposal_status=FounderProposalStatus.APPROVED)
    )

    with pytest.raises(AppError) as exc:
        await service.decide_proposal(ORG, ACTOR_ID, expired_id, approve=True)

    assert exc.value.code == "founder_proposal.not_pending"
    proposals.mark_expired.assert_not_awaited()
    session.rollback.assert_awaited_once()


async def test_expiry_sweeps_lock_approval_before_proposal(monkeypatch) -> None:
    """Both sweeps use the same approval-first lock order as decisions."""
    proposals, approvals = _RacyProposals(), _RacyApprovals()
    session, _ = _patch_founder_flow(monkeypatch, proposals, approvals)
    due = [
        SimpleNamespace(
            id=uuid.uuid4(),
            organization_id=ORG,
            proposal_status=FounderProposalStatus.PROPOSED,
            expires_at=NOW - timedelta(seconds=1),
            approval_request_id=REQ_ID,
        )
    ]
    proposals.list_pending_expired = AsyncMock(return_value=due)
    proposals.list_pending_expired_all = AsyncMock(return_value=due)
    order: list[str] = []

    async def _expire_approval(*args, **kwargs):
        order.append("approval")
        return True

    async def _expire_proposal(*args, **kwargs):
        order.append("proposal")
        return True

    proposals.mark_expired = AsyncMock(side_effect=_expire_proposal)
    approval_repo = MagicMock()
    approval_repo.mark_expired = AsyncMock(side_effect=_expire_approval)
    monkeypatch.setattr(
        "app.services.founder_action_service.ApprovalRequestRepository",
        MagicMock(return_value=approval_repo),
    )

    service = FounderActionService(session)
    assert await service.expire_due(ORG, now=NOW) == 1
    assert order == ["approval", "proposal"]
    order.clear()
    assert await service.expire_due_all(now=NOW) == 1
    assert order == ["approval", "proposal"]


# -- assignee validation ----------------------------------------------


async def test_foreign_and_inactive_assignees_create_no_task(monkeypatch) -> None:
    tasks = MagicMock()
    tasks.add = MagicMock()
    monkeypatch.setattr(
        "app.services.founder_action_service.TaskRepository", MagicMock(return_value=tasks)
    )
    service = FounderActionService(MagicMock())

    foreign_id = uuid.uuid4()
    users = MagicMock()
    users.get_or_404 = AsyncMock(side_effect=AppError("user.not_found", "not found", 404))
    monkeypatch.setattr(
        "app.services.founder_action_service.UserRepository", MagicMock(return_value=users)
    )
    proposal = SimpleNamespace(
        organization_id=ORG,
        title="Follow up",
        action_type=FounderActionType.CREATE_TASK,
        payload={"title": "Follow up", "assignee_user_id": str(foreign_id)},
    )
    with pytest.raises(AppError) as exc:
        await service._execute_create_task(proposal, actor=SimpleNamespace(id=ACTOR_ID))
    assert exc.value.code == "user.not_found"
    tasks.add.assert_not_called()

    users.get_or_404 = AsyncMock(return_value=SimpleNamespace(id=foreign_id, is_active=False))
    with pytest.raises(AppError) as exc:
        await service._execute_create_task(proposal, actor=SimpleNamespace(id=ACTOR_ID))
    assert exc.value.code == "task.invalid_assignee"
    tasks.add.assert_not_called()

    with pytest.raises(AppError) as exc:
        bad = SimpleNamespace(
            organization_id=ORG,
            title="Follow up",
            action_type=FounderActionType.CREATE_TASK,
            payload={"title": "Follow up", "assignee_user_id": "not-a-uuid"},
        )
        await service._execute_create_task(bad, actor=SimpleNamespace(id=ACTOR_ID))
    assert exc.value.code == "task.invalid_assignee"
    tasks.add.assert_not_called()


async def test_active_assignee_is_scoped_to_the_proposal_org(monkeypatch) -> None:
    assignee_id = uuid.uuid4()
    users = MagicMock()
    users.get_or_404 = AsyncMock(return_value=SimpleNamespace(id=assignee_id, is_active=True))
    monkeypatch.setattr(
        "app.services.founder_action_service.UserRepository", MagicMock(return_value=users)
    )
    tasks = MagicMock()
    tasks.add = MagicMock()
    monkeypatch.setattr(
        "app.services.founder_action_service.TaskRepository", MagicMock(return_value=tasks)
    )
    session = MagicMock()
    session.flush = AsyncMock()
    service = FounderActionService(session)
    proposal = SimpleNamespace(
        organization_id=ORG,
        title="Follow up",
        action_type=FounderActionType.CREATE_TASK,
        payload={"title": "Follow up", "assignee_user_id": str(assignee_id)},
    )

    reference = await service._execute_create_task(proposal, actor=SimpleNamespace(id=ACTOR_ID))
    users.get_or_404.assert_awaited_once_with(ORG, assignee_id)
    task = tasks.add.call_args.args[0]
    assert task.assignee_user_id == assignee_id
    assert task.organization_id == ORG
    assert reference["task_id"] == str(task.id)


async def test_bad_assignee_leaves_safe_failed_proposal(monkeypatch) -> None:
    proposals, approvals = _RacyProposals(), _RacyApprovals()
    session, tasks = _patch_founder_flow(monkeypatch, proposals, approvals)
    monkeypatch.setattr(
        "app.services.founder_action_service.UserRepository",
        MagicMock(
            return_value=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=ACTOR_ID, is_active=True)),
                get_or_404=AsyncMock(side_effect=AppError("user.not_found", "not found", 404)),
            )
        ),
    )
    foreign_id = uuid.uuid4()
    original_get = proposals.get

    async def _get(org, pid):
        obj = await original_get(org, pid)
        obj.payload = {"title": "Follow up", "assignee_user_id": str(foreign_id)}
        return obj

    proposals.get = AsyncMock(side_effect=_get)
    service = FounderActionService(session)

    result = await service.decide_proposal(ORG, ACTOR_ID, uuid.uuid4(), approve=True)
    assert result.proposal_status is FounderProposalStatus.FAILED
    assert result.execution_reference == {
        "error": "execution failed; see logs",
        "code": "user.not_found",
    }
    assert proposals.finish_calls[-1][0] is FounderProposalStatus.FAILED
    tasks.add.assert_not_called()
