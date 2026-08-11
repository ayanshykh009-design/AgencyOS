"""Unit tests for ApprovalGateService: gate decision + stamping (M6)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.models.enums import ApprovalRequestStatus, ExecutionStatus
from app.services.approval_gate_service import ApprovalGateService

ORG_ID = uuid.uuid4()
EXEC_ID = uuid.uuid4()
REQ_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _req(status: ApprovalRequestStatus, *, execution_id=EXEC_ID) -> SimpleNamespace:
    return SimpleNamespace(
        id=REQ_ID,
        organization_id=ORG_ID,
        workflow_execution_id=execution_id,
        status=status,
        decided_by_user_id=USER_ID,
    )


def _execution(status: ExecutionStatus) -> SimpleNamespace:
    return SimpleNamespace(status=status)


def _patch_gate_service(monkeypatch) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()

    approvals = MagicMock()
    executions = MagicMock()
    exec_svc = MagicMock()
    exec_svc.retry = AsyncMock()
    exec_svc.cancel = AsyncMock()

    monkeypatch.setattr(
        "app.services.approval_gate_service.ApprovalRequestRepository",
        MagicMock(return_value=approvals),
    )
    monkeypatch.setattr(
        "app.services.approval_gate_service.WorkflowExecutionRepository",
        MagicMock(return_value=executions),
    )
    monkeypatch.setattr(
        "app.services.approval_gate_service.WorkflowExecutionService",
        MagicMock(return_value=exec_svc),
    )
    return session, approvals, executions, exec_svc


def _svc(session) -> ApprovalGateService:
    return ApprovalGateService(session)


# -- gate action decision --------------------------------------------


def test_approved_requeues_terminal_states() -> None:
    for status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED, ExecutionStatus.TIMED_OUT):
        assert (
            ApprovalGateService._gate_action(ApprovalRequestStatus.APPROVED, _execution(status))
            == "retry"
        )


def test_approved_no_action_for_queued() -> None:
    assert (
        ApprovalGateService._gate_action(
            ApprovalRequestStatus.APPROVED, _execution(ExecutionStatus.QUEUED)
        )
        is None
    )
    assert (
        ApprovalGateService._gate_action(
            ApprovalRequestStatus.APPROVED, _execution(ExecutionStatus.SUCCEEDED)
        )
        is None
    )


def test_deny_cancels_active_states() -> None:
    for status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING, ExecutionStatus.RETRYING):
        for gate_status in (
            ApprovalRequestStatus.DENIED,
            ApprovalRequestStatus.EXPIRED,
            ApprovalRequestStatus.CANCELLED,
        ):
            assert ApprovalGateService._gate_action(gate_status, _execution(status)) == "cancel"


def test_deny_moot_for_settled() -> None:
    assert (
        ApprovalGateService._gate_action(
            ApprovalRequestStatus.DENIED, _execution(ExecutionStatus.SUCCEEDED)
        )
        is None
    )


def test_gate_action_none_when_no_execution() -> None:
    assert ApprovalGateService._gate_action(ApprovalRequestStatus.APPROVED, None) is None


# -- gate processing -------------------------------------------------


def test_process_gate_approved_retries(monkeypatch) -> None:
    session, approvals, executions, exec_svc = _patch_gate_service(monkeypatch)
    req = _req(ApprovalRequestStatus.APPROVED)
    approvals.claim_gate = AsyncMock(return_value=True)
    executions.get = AsyncMock(return_value=_execution(ExecutionStatus.FAILED))

    async def run() -> None:
        assert await _svc(session)._process_gate(req) is True

    import asyncio

    asyncio.run(run())
    exec_svc.retry.assert_awaited_once_with(ORG_ID, EXEC_ID, actor_user_id=USER_ID)
    exec_svc.cancel.assert_not_awaited()
    session.commit.assert_awaited_once()


def test_process_gate_denied_cancels(monkeypatch) -> None:
    session, approvals, executions, exec_svc = _patch_gate_service(monkeypatch)
    req = _req(ApprovalRequestStatus.DENIED)
    approvals.claim_gate = AsyncMock(return_value=True)
    executions.get = AsyncMock(return_value=_execution(ExecutionStatus.QUEUED))

    async def run() -> None:
        assert await _svc(session)._process_gate(req) is True

    import asyncio

    asyncio.run(run())
    exec_svc.cancel.assert_awaited_once_with(ORG_ID, EXEC_ID, cancelled_by_user_id=USER_ID)
    exec_svc.retry.assert_not_awaited()


def test_process_gate_stamps_without_op_when_moot(monkeypatch) -> None:
    session, approvals, executions, exec_svc = _patch_gate_service(monkeypatch)
    req = _req(ApprovalRequestStatus.APPROVED)
    approvals.claim_gate = AsyncMock(return_value=True)
    executions.get = AsyncMock(return_value=_execution(ExecutionStatus.QUEUED))

    async def run() -> None:
        assert await _svc(session)._process_gate(req) is True

    import asyncio

    asyncio.run(run())
    exec_svc.retry.assert_not_awaited()
    exec_svc.cancel.assert_not_awaited()
    session.commit.assert_awaited_once()


def test_process_gate_stamps_only_when_no_execution(monkeypatch) -> None:
    session, approvals, executions, exec_svc = _patch_gate_service(monkeypatch)
    req = _req(ApprovalRequestStatus.APPROVED, execution_id=None)
    approvals.claim_gate = AsyncMock(return_value=True)

    async def run() -> None:
        assert await _svc(session)._process_gate(req) is True

    import asyncio

    asyncio.run(run())
    approvals.claim_gate.assert_awaited_once()
    exec_svc.retry.assert_not_awaited()


def test_process_gate_loses_claim_race(monkeypatch) -> None:
    session, approvals, executions, exec_svc = _patch_gate_service(monkeypatch)
    req = _req(ApprovalRequestStatus.APPROVED)
    approvals.claim_gate = AsyncMock(return_value=False)
    executions.get = AsyncMock(return_value=_execution(ExecutionStatus.FAILED))

    async def run() -> None:
        assert await _svc(session)._process_gate(req) is False

    import asyncio

    asyncio.run(run())
    exec_svc.retry.assert_not_awaited()
    exec_svc.cancel.assert_not_awaited()
    session.commit.assert_not_awaited()


# -- sweep -----------------------------------------------------------


def test_sweep_handles_up_to_limit(monkeypatch) -> None:
    session, approvals, executions, exec_svc = _patch_gate_service(monkeypatch)
    req = _req(ApprovalRequestStatus.DENIED)
    approvals.list_unhandled_gates = AsyncMock(return_value=[req, req, req])
    approvals.claim_gate = AsyncMock(return_value=True)
    executions.get = AsyncMock(return_value=_execution(ExecutionStatus.QUEUED))

    async def run() -> None:
        assert await _svc(session).sweep(limit=50) == 3

    import asyncio

    asyncio.run(run())
    assert exec_svc.cancel.await_count == 3
