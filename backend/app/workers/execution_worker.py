"""Execution worker: drains the workflow execution queue.

The worker sweeps the global execution queue on a polling loop:

- requeues due RETRYING executions,
- drains QUEUED executions through the adapter selected by the workflow's
  ``execution_mode``,
- marks stale RUNNING executions as ``timed_out``.

It owns a session per phase and is safe to run on multiple instances (state
transitions are optimistic — only one runner moves an execution out of
QUEUED/RETRYING/RUNNING).

Runs as a standalone loop (``python -m app.workers.execution_worker``) or as a
single sweep from a scheduler.
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.enums import WorkflowStatus
from app.repositories.workflow import WorkflowRepository
from app.services.execution_adapter import get_adapter
from app.services.workflow_execution_service import WorkflowExecutionService

logger = logging.getLogger("agencyos.automation.worker")


class ExecutionWorker:
    """Sweep the global execution queue through the adapters."""

    @classmethod
    async def process_retries(cls) -> int:
        """Requeue executions whose retry window has elapsed."""
        async with async_session_factory() as session:
            service = WorkflowExecutionService(session)
            executions = await service.get_queued_for_retry()
            for execution in executions:
                await service.retry(execution.organization_id, execution.id)
            await session.commit()
            return len(executions)

    @classmethod
    async def process_queued(cls, batch_size: int = 10) -> int:
        """Run QUEUED executions through the workflow's adapter."""
        async with async_session_factory() as session:
            service = WorkflowExecutionService(session)
            workflow_repo = WorkflowRepository(session)
            executions = await service.get_queued(batch_size)
            for execution in executions:
                workflow = await workflow_repo.get(
                    execution.organization_id, execution.workflow_id
                )
                if workflow is None or workflow.status != WorkflowStatus.ACTIVE:
                    await service.fail(
                        execution.organization_id,
                        execution.id,
                        error={
                            "error": "workflow_unavailable",
                            "message": "Workflow is not active or not found",
                        },
                        schedule_retry=False,
                    )
                    continue

                await service.start(execution.organization_id, execution.id)
                adapter = get_adapter(workflow.execution_mode)
                try:
                    output = await adapter.execute(
                        workflow_id=execution.workflow_id,
                        execution_id=execution.id,
                        input_data=execution.input,
                        config=workflow.config,
                    )
                except Exception as exc:
                    logger.exception(
                        "execution %s failed via %s adapter",
                        execution.id,
                        workflow.execution_mode,
                    )
                    await service.fail(
                        execution.organization_id,
                        execution.id,
                        error={"error": "adapter_error", "message": str(exc)},
                        schedule_retry=True,
                    )
                else:
                    await service.complete(
                        execution.organization_id,
                        execution.id,
                        output=output,
                    )
            await session.commit()
            return len(executions)

    @classmethod
    async def timeout_stuck(cls) -> int:
        """Mark RUNNING executions that exceeded the timeout as timed out."""
        async with async_session_factory() as session:
            service = WorkflowExecutionService(session)
            executions = await service.get_stuck_running()
            for execution in executions:
                await service.timeout(execution.organization_id, execution.id)
            await session.commit()
            return len(executions)

    @classmethod
    async def sweep(cls) -> dict[str, int]:
        """Run one full pass: retries + queued + timeouts."""
        retried = await cls.process_retries()
        processed = await cls.process_queued()
        timed_out = await cls.timeout_stuck()
        return {"retried": retried, "processed": processed, "timed_out": timed_out}

    @classmethod
    async def run_loop(cls) -> None:
        """Poll forever: the standalone worker entrypoint."""
        logger.info(
            "execution worker starting (poll %ss)",
            settings.EXECUTION_POLL_INTERVAL_SECONDS,
        )
        while True:
            try:
                stats = await cls.sweep()
                if any(stats.values()):
                    logger.info("execution worker sweep: %s", stats)
            except Exception:
                logger.exception("execution worker sweep failed")
            await asyncio.sleep(settings.EXECUTION_POLL_INTERVAL_SECONDS)


def _worker_entrypoint() -> None:
    """Entrypoint for ``python -m app.workers.execution_worker``."""
    asyncio.run(ExecutionWorker.run_loop())


if __name__ == "__main__":
    _worker_entrypoint()
