"""Approval gate worker service (M6).

Sweeps terminal approval requests whose gate has not been applied to the
linked workflow execution yet. For each:

- APPROVED     -> resume the gated execution: FAILED/CANCELLED/TIMED_OUT are
                  requeued via ``WorkflowExecutionService.retry()``; QUEUED
                  executions are picked up automatically by the execution
                  worker once the pending gate closes.
- DENIED/EXPIRED/CANCELLED -> cancel the gated execution (QUEUED/RUNNING/
                  RETRYING), otherwise the decision is moot.

``gate_handled_at`` is stamped in the same transaction as the execution op,
which makes processing idempotent: a crash rolls the stamp back and the next
sweep retries; a concurrent worker loses the stamp race.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ApprovalRequestStatus, ExecutionStatus
from app.repositories.approval_request import ApprovalRequestRepository
from app.repositories.workflow_execution import WorkflowExecutionRepository
from app.services.base import commit_with_retry, utcnow
from app.services.workflow_execution_service import WorkflowExecutionService

logger = logging.getLogger("agencyos.communication.gate")


class ApprovalGateService:
    """Applies terminal approval decisions to gated workflow executions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._approvals = ApprovalRequestRepository(session)
        self._executions = WorkflowExecutionRepository(session)
        self._exec_svc = WorkflowExecutionService(session)

    async def sweep(self, *, limit: int = 50) -> int:
        """Process up to ``limit`` unhandled gates; returns count handled."""
        handled = 0
        requests = await self._approvals.list_unhandled_gates(limit=limit)
        for req in requests:
            if await self._process_gate(req):
                handled += 1
        return handled

    async def _process_gate(self, req) -> bool:
        """Handle one gate; returns True if gate_handled_at was stamped."""
        if req.workflow_execution_id is None:
            # No gated execution; just stamp and move on.
            claimed = await self._approvals.claim_gate(req.id, handled_at=utcnow())
            if claimed:
                await commit_with_retry(self._session)
            return claimed

        exec_id = req.workflow_execution_id
        org_id = req.organization_id
        execution = await self._executions.get(org_id, exec_id)

        action = self._gate_action(req.status, execution)
        # Stamp first: the execution op and the stamp commit together, so a
        # crash rolls both back and the sweep retries; a concurrent worker
        # loses the stamp race.
        claimed = await self._approvals.claim_gate(req.id, handled_at=utcnow())
        if not claimed:
            return False  # Another worker beat us.

        try:
            if action == "retry":
                await self._exec_svc.retry(
                    org_id, exec_id, actor_user_id=req.decided_by_user_id
                )
                logger.info("gate approved -> execution %s requeued", exec_id)
            elif action == "cancel":
                await self._exec_svc.cancel(
                    org_id,
                    exec_id,
                    cancelled_by_user_id=req.decided_by_user_id,
                )
                logger.info(
                    "gate %s -> execution %s cancelled", req.status.value, exec_id
                )
            else:
                logger.info(
                    "gate %s -> execution %s already settled; stamping handled",
                    req.status.value,
                    exec_id,
                )

            await commit_with_retry(self._session)
            return True
        except Exception:  # pragma: no cover - defensive
            # The execution op failed (e.g. state changed concurrently).
            # Rollback reverts the gate stamp; the next sweep re-evaluates.
            logger.exception("gate processing failed for request %s", req.id)
            await self._session.rollback()
            raise

    @staticmethod
    def _gate_action(
        status: ApprovalRequestStatus, execution
    ) -> str | None:
        """Decide the execution action for a terminal approval status.

        Returns ``"retry"``, ``"cancel"``, or ``None`` (decision is moot — the
        execution already settled and the gate should just be stamped).
        """
        if execution is None:
            return None

        if status == ApprovalRequestStatus.APPROVED:
            if execution.status in (
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
                ExecutionStatus.TIMED_OUT,
            ):
                return "retry"
            return None  # QUEUED resumes via the worker; RUNNING/SUCCEEDED moot.

        if execution.status in (
            ExecutionStatus.QUEUED,
            ExecutionStatus.RUNNING,
            ExecutionStatus.RETRYING,
        ):
            return "cancel"
        return None
