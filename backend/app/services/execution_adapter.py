"""Workflow execution adapters — strategy pattern for dispatching executions.

Phase 5A ships two adapters:
- N8nAdapter: dispatches to an n8n workflow via webhook.
- BuiltinAdapter: runs a declarative step definition in-process (Phase 5B).

The adapter is selected based on the workflow's ``execution_mode`` field.
"""
from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.core.metrics import get_counter
from app.services.builtin_execution import (
    BuiltinExecutionError,
    run_builtin_definition,
)
from app.services.n8n_client import N8nClient

logger = logging.getLogger("agencyos.automation.adapter")


class ExecutionAdapter(ABC):
    """Base class for workflow execution adapters."""

    @abstractmethod
    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute the workflow and return the result payload."""
        ...


class N8nAdapter(ExecutionAdapter):
    """Dispatch workflow execution to an n8n instance via webhook."""

    def __init__(self, client: N8nClient | None = None) -> None:
        self._client = client or N8nClient()

    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        webhook_path = config.get("webhook_path", f"/webhook/workflow-{workflow_id}")
        payload = {
            "execution_id": str(execution_id),
            "workflow_id": str(workflow_id),
            "input": input_data,
        }
        logger.info("Dispatching to n8n: %s", webhook_path)
        result = await self._client.trigger_webhook(webhook_path, payload)
        logger.info("n8n response for execution %s: %s", execution_id, result)
        return result


class BuiltinAdapter(ExecutionAdapter):
    """In-process execution via the declarative step engine.

    Runs ``definition`` against ``input_data`` deterministically and returns
    the produced result payload. Failures surface as exceptions so the
    execution worker's existing retry/timeout machinery applies unchanged;
    the engine itself leaves no state behind, keeping retries restart-safe.
    """

    async def execute(
        self,
        workflow_id: uuid.UUID,
        execution_id: uuid.UUID,
        input_data: dict[str, Any],
        config: dict[str, Any],
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        definition = definition or {}
        get_counter(
            "builtin_execution_started",
            description="Builtin workflow executions started",
        ).add()
        logger.info(
            "builtin execution start: execution=%s workflow=%s",
            execution_id,
            workflow_id,
        )
        try:
            result = run_builtin_definition(definition, input_data)
        except BuiltinExecutionError as exc:
            get_counter(
                "builtin_execution_failed",
                description="Builtin workflow executions that failed",
            ).add()
            logger.warning(
                "builtin execution failed: execution=%s error=%s",
                execution_id,
                exc,
            )
            raise
        except Exception:
            get_counter(
                "builtin_execution_failed",
                description="Builtin workflow executions that failed",
            ).add()
            logger.exception("builtin execution errored: execution=%s", execution_id)
            raise
        get_counter(
            "builtin_execution_succeeded",
            description="Builtin workflow executions that succeeded",
        ).add()
        logger.info(
            "builtin execution success: execution=%s workflow=%s",
            execution_id,
            workflow_id,
        )
        return result


def get_adapter(execution_mode: str) -> ExecutionAdapter:
    """Return the appropriate adapter for the given execution mode."""
    adapters: dict[str, type[ExecutionAdapter]] = {
        "n8n": N8nAdapter,
        "builtin": BuiltinAdapter,
    }
    adapter_cls = adapters.get(execution_mode)
    if adapter_cls is None:
        raise ValueError(f"Unknown execution mode: {execution_mode}")
    return adapter_cls()
