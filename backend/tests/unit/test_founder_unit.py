"""Unit tests for the Founder AI Assistant (M8) — no database required.

These cover the deterministic, testable pieces of M8:
- intent routing (FounderIntentService)
- grounded context snapshot (FounderContext)
- founder-native tools (param validation + approval routing)
- guarded proposal lifecycle transitions (repository)
- FounderActionService propose / decide / expire (mocked deps)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.founder_context import FounderContext
from app.core.errors import AppError
from app.models.enums import (
    FounderActionType,
    FounderProposalStatus,
)
from app.repositories.founder_action_proposal import (
    FounderActionProposalRepository,
)
from app.services.founder_action_service import (
    FounderActionService,
)
from app.services.founder_intent_service import (
    FounderIntentService,
    FounderIntentType,
)
from app.tools.founder_tools import (
    CreateTaskTool,
    FounderToolContext,
    ProposeFounderActionTool,
    SummarizeContextTool,
)

# --------------------------------------------------------------------------- #
# Intent routing
# --------------------------------------------------------------------------- #


def test_classify_status_question() -> None:
    intent = FounderIntentService.classify("How many leads do we have this week?")
    assert intent.intent_type == FounderIntentType.STATUS
    assert intent.requires_approval is False
    assert "summarize_context" in intent.suggested_tools


def test_classify_action_keyword() -> None:
    intent = FounderIntentService.classify("Please create a task to follow up with Acme")
    assert intent.intent_type == FounderIntentType.ACTION
    assert intent.requires_approval is True
    assert "create_task" in intent.suggested_tools


def test_classify_greeting_is_casual() -> None:
    assert FounderIntentService.classify("hi").intent_type == FounderIntentType.CASUAL
    assert (
        FounderIntentService.classify("good morning team").intent_type
        == FounderIntentType.CASUAL
    )


def test_classify_empty_defaults_to_read_only() -> None:
    intent = FounderIntentService.classify("")
    assert intent.intent_type == FounderIntentType.CASUAL
    assert intent.requires_approval is False


def test_classify_brainstorm() -> None:
    intent = FounderIntentService.classify("What if we changed our pricing strategy?")
    assert intent.intent_type == FounderIntentType.BRAINSTORM
    assert intent.requires_approval is False


# --------------------------------------------------------------------------- #
# FounderContext snapshot
# --------------------------------------------------------------------------- #


def test_context_summary_and_to_dict() -> None:
    ctx = FounderContext(
        organization_id=uuid.uuid4(),
        organization_name="Acme",
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        leads=[{"name": "A", "company": "C", "status": "new"}],
        tasks=[],
        kpi={"revenue": 100},
    )
    summary = ctx.summary()
    assert "Acme" in summary
    assert "revenue" in summary
    snapshot = ctx.to_dict()
    assert snapshot["organization_name"] == "Acme"
    assert snapshot["kpi"] == {"revenue": 100}


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


def _tool_ctx(action_service: MagicMock) -> FounderToolContext:
    org = uuid.uuid4()
    context = FounderContext(
        organization_id=org,
        organization_name="Acme",
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        leads=[{"name": "A", "company": "C", "status": "new"}],
    )
    return FounderToolContext(
        session=MagicMock(),
        organization_id=org,
        context=context,
        action_service=action_service,
        conversation_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
    )


async def test_summarize_tool_returns_context() -> None:
    tool = SummarizeContextTool(_tool_ctx(MagicMock()))
    res = await tool.run({})
    assert res.ok
    assert "Acme" in res.content


async def test_create_task_tool_happy_path() -> None:
    proposal = SimpleNamespace(
        id=uuid.uuid4(),
        title="Create task: Follow up",
        proposal_status=FounderProposalStatus.PROPOSED,
    )
    action = MagicMock()
    action.propose = AsyncMock(return_value=proposal)
    tool = CreateTaskTool(_tool_ctx(action))
    res = await tool.run({"title": "Follow up"})
    assert res.ok
    assert res.content["requires_approval"] is True
    action.propose.assert_awaited_once()


async def test_create_task_tool_rejects_blank_title() -> None:
    tool = CreateTaskTool(_tool_ctx(MagicMock()))
    res = await tool.run({"title": "   "})
    assert res.ok is False


async def test_propose_action_rejects_unknown_type() -> None:
    tool = ProposeFounderActionTool(_tool_ctx(MagicMock()))
    res = await tool.run({"action_type": "nonsense", "title": "X"})
    assert res.ok is False


async def test_propose_action_rejects_missing_title() -> None:
    tool = ProposeFounderActionTool(_tool_ctx(MagicMock()))
    res = await tool.run({"action_type": "create_task"})
    assert res.ok is False


async def test_propose_action_happy_path() -> None:
    proposal = SimpleNamespace(
        id=uuid.uuid4(),
        title="t",
        proposal_status=FounderProposalStatus.PROPOSED,
    )
    action = MagicMock()
    action.propose = AsyncMock(return_value=proposal)
    tool = ProposeFounderActionTool(_tool_ctx(action))
    res = await tool.run(
        {"action_type": "create_task", "title": "t", "justification": "j"}
    )
    assert res.ok
    action.propose.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Guarded lifecycle transitions
# --------------------------------------------------------------------------- #


def _proposal(status: FounderProposalStatus) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        proposal_status=status,
        expires_at=None,
        decided_at=None,
        decided_by_user_id=None,
        execution_reference=None,
    )


def test_apply_transition_legal_edge() -> None:
    repo = FounderActionProposalRepository(MagicMock())
    p = _proposal(FounderProposalStatus.PROPOSED)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    repo.apply_transition(
        p, FounderProposalStatus.APPROVED, now=now, decided_by_user_id=uuid.uuid4()
    )
    assert p.proposal_status == FounderProposalStatus.APPROVED
    assert p.decided_at == now


def test_apply_transition_illegal_edge_raises() -> None:
    repo = FounderActionProposalRepository(MagicMock())
    p = _proposal(FounderProposalStatus.APPROVED)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(AppError):
        repo.apply_transition(
            p, FounderProposalStatus.SUCCEEDED, now=now, decided_by_user_id=uuid.uuid4()
        )


def test_apply_transition_terminal_is_immutable() -> None:
    repo = FounderActionProposalRepository(MagicMock())
    p = _proposal(FounderProposalStatus.SUCCEEDED)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(AppError):
        repo.apply_transition(
            p, FounderProposalStatus.PROPOSED, now=now, decided_by_user_id=uuid.uuid4()
        )


# --------------------------------------------------------------------------- #
# FounderActionService (mocked dependencies)
# --------------------------------------------------------------------------- #


def _patch_action_service(monkeypatch, *, proposal=None, proposals_repo=None):
    org = uuid.uuid4()
    actor_id = uuid.uuid4()

    user = SimpleNamespace(id=actor_id)
    monkeypatch.setattr(
        "app.services.founder_action_service.UserRepository",
        MagicMock(
            return_value=SimpleNamespace(get=AsyncMock(return_value=user))
        ),
    )

    approval_svc = MagicMock()
    approval_svc.create_request = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    approval_svc.decide = AsyncMock()
    monkeypatch.setattr(
        "app.services.founder_action_service.ApprovalService",
        lambda *a, **k: approval_svc,
    )

    if proposals_repo is None:
        proposals_repo = MagicMock()
        proposals_repo.get = AsyncMock(return_value=proposal)
        proposals_repo.add = MagicMock()
        proposals_repo.apply_transition = MagicMock()
        proposals_repo.mark_expired = AsyncMock(return_value=True)
        proposals_repo.list_pending_expired_all = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.founder_action_service.FounderActionProposalRepository",
        lambda *a, **k: proposals_repo,
    )
    monkeypatch.setattr(
        "app.services.founder_action_service.ApprovalRequestRepository",
        MagicMock(return_value=SimpleNamespace(mark_expired=AsyncMock())),
    )
    monkeypatch.setattr(
        "app.services.founder_action_service.commit_with_retry", AsyncMock()
    )
    monkeypatch.setattr(
        "app.services.founder_action_service.utcnow",
        lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    # The per-org AI kill switch is enforced inside ``decide_proposal`` but is
    # exercised exhaustively by the dedicated kill-switch tests; here we keep
    # AI enabled so the founder decision-logic tests can proceed.
    monkeypatch.setattr(
        "app.services.ai_service.AIService.assert_ai_enabled",
        AsyncMock(),
    )
    return org, actor_id, approval_svc, proposals_repo


async def test_propose_creates_pending_gated_proposal(monkeypatch) -> None:

    org, actor_id, approval_svc, _ = _patch_action_service(monkeypatch)
    svc = FounderActionService(MagicMock())
    proposal = await svc.propose(
        organization_id=org,
        actor_user_id=actor_id,
        conversation_id=None,
        action_type=FounderActionType.CREATE_TASK,
        title="Create task: Follow up",
        payload={"title": "Follow up", "priority": "high"},
        justification="because",
    )
    assert proposal.proposal_status == FounderProposalStatus.PROPOSED
    assert proposal.title == "Create task: Follow up"
    assert approval_svc.create_request.await_count == 1


async def test_decide_approve_create_task_executes(monkeypatch) -> None:
    proposal = _proposal(FounderProposalStatus.PROPOSED)
    proposal.id = uuid.uuid4()
    proposal.organization_id = uuid.uuid4()
    proposal.action_type = FounderActionType.CREATE_TASK
    proposal.approval_request_id = uuid.uuid4()
    proposal.payload = {"title": "Follow up", "priority": "high"}
    proposal.execution_reference = None

    org, actor_id, approval_svc, proposals_repo = _patch_action_service(
        monkeypatch, proposal=proposal
    )
    session = MagicMock()
    session.flush = AsyncMock()
    svc = FounderActionService(session)
    result = await svc.decide_proposal(org, actor_id, proposal.id, approve=True)

    assert approval_svc.decide.await_count == 1
    applied = [c.args[1] for c in proposals_repo.apply_transition.call_args_list]
    assert FounderProposalStatus.APPROVED in applied
    assert FounderProposalStatus.EXECUTING in applied
    assert FounderProposalStatus.SUCCEEDED in applied
    assert result.execution_reference is not None


async def test_decide_deny_marks_denied(monkeypatch) -> None:
    proposal = _proposal(FounderProposalStatus.PROPOSED)
    proposal.id = uuid.uuid4()
    proposal.organization_id = uuid.uuid4()
    proposal.action_type = FounderActionType.CREATE_TASK
    proposal.approval_request_id = uuid.uuid4()
    proposal.payload = {}

    org, actor_id, approval_svc, proposals_repo = _patch_action_service(
        monkeypatch, proposal=proposal
    )
    svc = FounderActionService(MagicMock())
    await svc.decide_proposal(org, actor_id, proposal.id, approve=False)
    applied = [c.args[1] for c in proposals_repo.apply_transition.call_args_list]
    assert FounderProposalStatus.DENIED in applied


async def test_decide_rejects_non_pending(monkeypatch) -> None:
    from app.core.errors import AppError

    proposal = _proposal(FounderProposalStatus.SUCCEEDED)
    proposal.id = uuid.uuid4()
    proposal.organization_id = uuid.uuid4()
    proposal.action_type = FounderActionType.CREATE_TASK
    proposal.approval_request_id = uuid.uuid4()

    org, actor_id, _, _ = _patch_action_service(monkeypatch, proposal=proposal)
    svc = FounderActionService(MagicMock())
    with pytest.raises(AppError):
        await svc.decide_proposal(org, actor_id, proposal.id, approve=True)


async def test_get_proposal_404_when_missing(monkeypatch) -> None:
    from app.core.errors import AppError

    org, actor_id, _, _ = _patch_action_service(monkeypatch, proposal=None)
    svc = FounderActionService(MagicMock())
    with pytest.raises(AppError):
        await svc.get_proposal(org, uuid.uuid4())


async def test_expire_due_all_sweeps_expired(monkeypatch) -> None:
    expired = _proposal(FounderProposalStatus.PROPOSED)
    expired.id = uuid.uuid4()
    expired.organization_id = uuid.uuid4()
    expired.approval_request_id = uuid.uuid4()

    proposals_repo = MagicMock()
    proposals_repo.list_pending_expired_all = AsyncMock(return_value=[expired])
    proposals_repo.mark_expired = AsyncMock(return_value=True)
    org, actor_id, _, _ = _patch_action_service(
        monkeypatch, proposals_repo=proposals_repo
    )
    svc = FounderActionService(MagicMock())
    handled = await svc.expire_due_all()
    assert handled == 1
